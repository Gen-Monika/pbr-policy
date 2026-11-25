/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Description
    Instrumented wrapper around GAMGPreconditioner, used to measure the cost
    scale r for algebraic multigrid.

    Why a wrapper and not a replica:
      Unlike DIC/DILU/FDIC -- whose setup is a single face loop that can be
      copied verbatim -- the AMG setup is the whole multigrid hierarchy and the
      apply is a V-cycle implemented in GAMGSolver's protected
      initVcycle/Vcycle. There is nothing small to replicate. So this class
      calls the REAL GAMG and measures it.

    What is measured:
      setup : the GAMGSolver base-class constructor, where ALL of GAMG's setup
              cost lives.
      apply : one call to GAMGPreconditioner::precondition() = nVcycles_ V-cycles
              (default 2).
      amul  : a replica of the internal lduMatrix::Amul loop, for the
              per-iteration denominator.

    Two-layer setup (important for interpretation):
      GAMGAgglomeration::New returns a MESH-LEVEL object found through the
      objectRegistry (mesh.thisDb().cfindObject<GAMGAgglomeration>), so the
      agglomeration hierarchy is built ONCE per mesh and shared. What is paid
      on every construction is the rest: matrixLevels_ (one coarse lduMatrix
      per level, via agglomerateMatrix), the interface levels, and the
      smoothers. That is why t_setup is expected (and observed) to be large on
      the first solve and smaller afterwards.

    Timing mechanics:
      The base-class constructor runs BEFORE the derived constructor body, so a
      timer started in the body would miss the setup. Instead TimerBase is
      listed first in the base list, so its constructor -- and therefore the
      clock read -- happens before GAMGPreconditioner's. The derived body then
      reads elapsed() as the setup time.

    Control (environment variables):
      PBR_GAMG_BENCH  : 1 = enable timing
      PBR_GAMG_OUT    : CSV to append records to
      PBR_GAMG_REPS   : repetitions for the apply/amul measurement (default 50,
                        because a single V-cycle is expensive relative to DIC)
      PBR_GAMG_AT     : comma-separated time indices to measure (unset = never)

    Output columns:
      timeIndex,field,nCells,nFaces,nVcycles,reps,t_setup,t_amul,t_apply,
      t_iter,r

\*---------------------------------------------------------------------------*/

#include "PBRGAMGPreconditioner.H"

#include "objectRegistry.H"
#include "Time.H"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <fstream>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

defineTypeNameAndDebug(PBRGAMGPreconditioner, 0);

lduMatrix::preconditioner::
    addsymMatrixConstructorToTable<PBRGAMGPreconditioner>
    addPBRGAMGPreconditionerSymMatrixConstructorToTable_;


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace
{
    //- Read an environment variable as a label; return fallback if unset
    label envLabel(const char* name, const label fallback)
    {
        const char* s = std::getenv(name);
        if (!s || !*s) return fallback;
        return static_cast<label>(std::strtol(s, nullptr, 10));
    }

    //- Read an environment variable as a string; return fallback if unset
    string envString(const char* name, const char* fallback)
    {
        const char* s = std::getenv(name);
        return string((s && *s) ? s : fallback);
    }

    //- Parse a comma-separated list of labels ("50,150,250"); empty if unset
    std::vector<label> envLabelList(const char* name)
    {
        std::vector<label> out;
        const char* s = std::getenv(name);
        if (!s || !*s) return out;

        const char* p = s;
        while (*p)
        {
            char* end = nullptr;
            const long v = std::strtol(p, &end, 10);
            if (end == p) break;
            out.push_back(static_cast<label>(v));
            p = end;
            while (*p == ',' || *p == ' ' || *p == '\t') ++p;
        }
        return out;
    }

    //- Monotonic wall-clock seconds
    double wallSeconds()
    {
        using namespace std::chrono;
        return duration<double>(steady_clock::now().time_since_epoch()).count();
    }
    //- Verbatim internal part of lduMatrix::Amul for a serial mesh
    void amulReplica
    (
        solveScalarField& wA,
        const solveScalarField& pA,
        const scalarField& diag,
        const scalarField& upper,
        const scalarField& lower,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        solveScalar* __restrict__ w = wA.begin();
        const solveScalar* __restrict__ p = pA.begin();
        const scalar* __restrict__ d = diag.begin();
        const scalar* __restrict__ up = upper.begin();
        const scalar* __restrict__ lo = lower.begin();
        const label* __restrict__ u = uAddr.begin();
        const label* __restrict__ l = lAddr.begin();

        const label nCells = wA.size();
        const label nFaces = upper.size();

        for (label cell=0; cell<nCells; cell++)
        {
            w[cell] = d[cell]*p[cell];
        }
        for (label face=0; face<nFaces; face++)
        {
            w[u[face]] += lo[face]*p[l[face]];
            w[l[face]] += up[face]*p[u[face]];
        }
    }
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::PBRGAMGPreconditioner::PBRGAMGPreconditioner
(
    const lduMatrix::solver& sol,
    const dictionary& solverControls
)
:
    TimerBase(),                    // clocks BEFORE GAMG's constructor runs
    GAMGPreconditioner(sol, solverControls),
    applyTimes_(),
    timeIndex_(sol.matrix().mesh().thisDb().time().timeIndex()),
    timing_(envLabel("PBR_GAMG_BENCH", 0) == 1),
    reps_(envLabel("PBR_GAMG_REPS", 50)),
    setupTime_(elapsed()),
    outPath_(envString("PBR_GAMG_OUT", ""))
{
    applyTimes_.reserve(reps_ > 0 ? reps_ + 4 : 0);

    if (!timing_) return;

    // Time indices to measure: unset means never
    const std::vector<label> benchAt = envLabelList("PBR_GAMG_AT");
    if (std::find(benchAt.begin(), benchAt.end(), timeIndex_) == benchAt.end())
    {
        return;
    }

    // One time index holds several p_rgh solves, each constructing its own
    // preconditioner. Measure only the first of them per index.
    {
        static std::set<std::pair<label, word>> done;
        if (!done.insert(std::make_pair(timeIndex_, sol.fieldName())).second)
        {
            return;
        }
    }

    report(sol.matrix());
}


// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

Foam::PBRGAMGPreconditioner::~PBRGAMGPreconditioner()
{}


// * * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

double Foam::PBRGAMGPreconditioner::median(std::vector<double> v)
{
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    const std::size_t n = v.size();
    return (n % 2) ? v[n/2] : 0.5*(v[n/2 - 1] + v[n/2]);
}


void Foam::PBRGAMGPreconditioner::report(const lduMatrix& M) const{
    const scalarField& diag = M.diag();
    const scalarField& upper = M.upper();
    const scalarField& lower = M.hasLower() ? M.lower() : M.upper();
    const labelList& uAddr = M.lduAddr().upperAddr();
    const labelList& lAddr = M.lduAddr().lowerAddr();

    const label nCells = diag.size();
    const label nFaces = upper.size();

    solveScalarField x(nCells, 1.0);
    solveScalarField wA(nCells, 0.0);

    std::vector<double> tAmul;
    tAmul.reserve(reps_);

    // Interleave amul and apply so transient load is common-mode.
    for (label rep=0; rep<reps_; rep++)
    {
        const double m0 = wallSeconds();
        amulReplica(wA, x, diag, upper, lower, uAddr, lAddr);
        const double m1 = wallSeconds();
        tAmul.push_back(m1 - m0);

        // precondition() is const; its own scratch allocations are part of the
        // measured apply cost, which is inherent to how GAMG applies a cycle.
        const double p0 = wallSeconds();
        this->precondition(wA, x, 0);
        const double p1 = wallSeconds();
        applyTimes_.push_back(p1 - p0);
    }

    const double ma = median(tAmul);
    const double mp = median(applyTimes_);
    const double iter = ma + mp;
    const double r = (iter > 0.0) ? setupTime_/iter : -1.0;

    if (!outPath_.empty())
    {
        std::ofstream os(outPath_.c_str(), std::ios::app);
        if (os.good())
        {
            os << timeIndex_ << ',' << fieldName_ << ','
               << nCells << ',' << nFaces << ','
               << nVcycles_ << ',' << reps_ << ','
               << setupTime_ << ',' << ma << ',' << mp << ','
               << iter << ',' << r << '\n';
        }
    }
}


void Foam::PBRGAMGPreconditioner::precondition
(
    solveScalarField& wA,
    const solveScalarField& rA,
    const direction cmpt
) const
{
    GAMGPreconditioner::precondition(wA, rA, cmpt);
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// ************************************************************************* //
