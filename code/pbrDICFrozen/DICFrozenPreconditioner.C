/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Description
    Freezeable DIC preconditioner for the IT[a,b] reuse experiment.

    Behaves exactly like DIC, except that the reciprocal preconditioned
    diagonal (rD_) can be frozen at a chosen time index "b" and then be
    reused for all later time indices "a >= b", instead of being recomputed
    from the current matrix.

    Rebuild (a <= b): rD_ computed from the matrix at time a   (normal DIC)
    Reuse   (a >  b): rD_ loaded from the freeze written at b  (this class)

    Control (environment variables):
      PBR_FREEZE_AT   : time index b at which to freeze (-1 = disabled)
      PBR_STORE       : directory for freeze files
      PBR_BENCH       : 1 = run the setup/apply/Amul micro-benchmark
      PBR_BENCH_AT    : time indices at which to run it, comma-separated
                        (e.g. "20,100,250"); unset = never
      PBR_BENCH_REPS  : repetitions (default 200)
      PBR_BENCH_OUT   : CSV to append the benchmark result to

    The field name (p_rgh, pcorr, ...) is taken automatically from
    sol.fieldName(), so different equations never share a freeze file.

    Note: the freeze persists across *separate* solver instances, which is
    what makes cross-timestep reuse observable. OpenFOAM constructs a fresh
    preconditioner per solver invocation (PCG.C guards with "if (!preconPtr_)"),
    so persistence must go through the file system.

    Micro-benchmark rationale (PBR_BENCH):
      The quantity "r" = setup cost / one-iteration cost decides whether a
      reuse-vs-rebuild DECISION SPACE exists at all. r must be measured on
      the real matrix, not estimated from a flop count: calcReciprocalD is a
      serial recurrence with random access (poorly vectorised), while the
      SpMV in Amul is parallel and vectorises well. A flop-based estimate
      therefore systematically understates r.

      lduMatrix::solver keeps interfaceBouCoeffs_ and interfaces_ protected,
      so a preconditioner subclass cannot call Amul directly. For a
      single-processor case the interface list is empty and Amul reduces to
      the internal loop, which is reproduced verbatim in amulReplica() using
      only public accessors (diag/upper/lower/lduAddr) -- the same ones DIC
      itself uses.

      The three timings are INTERLEAVED within one repetition loop so that
      transient machine load is common-mode across them, which is what makes
      the ratio meaningful on a shared, noisy box.

\*---------------------------------------------------------------------------*/

#include "DICFrozenPreconditioner.H"

// lduMesh only forward-declares objectRegistry; need the full definition
// to reach through thisDb().time().timeIndex().
#include "objectRegistry.H"
#include "Time.H"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <set>
#include <vector>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

defineTypeNameAndDebug(DICFrozenPreconditioner, 0);

lduMatrix::preconditioner::
    addsymMatrixConstructorToTable<DICFrozenPreconditioner>
    addDICFrozenPreconditionerSymMatrixConstructorToTable_;


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

    //- Parse a comma-separated list of labels ("20,100,250"); empty if unset
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
            if (end == p) break;            // no digits parsed
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

    //- Median of a sample (sorts in place)
    double median(std::vector<double>& v)
    {
        if (v.empty()) return 0.0;
        std::sort(v.begin(), v.end());
        const std::size_t n = v.size();
        return (n % 2) ? v[n/2] : 0.5*(v[n/2 - 1] + v[n/2]);
    }

    //- Verbatim internal part of lduMatrix::Amul for a serial mesh.
    //  Interfaces are empty in a single-processor run, so init/updateMatrixInterfaces
    //  are no-ops and this reproduces Amul's arithmetic exactly -- including the
    //  distinct lower/upper coefficients (equal here, but kept for fidelity).
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

    //- Verbatim DIC setup (OpenFOAM DICPreconditioner.C, calcReciprocalD).
    //  Kept as a free function taking an explicit rD so the benchmark can point
    //  several variants at the same matrix without touching the member state.
    void dicSetup
    (
        solveScalarField& rD,
        const scalarField& diag,
        const scalarField& upper,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        std::copy(diag.begin(), diag.end(), rD.begin());

        solveScalar* __restrict__ rDPtr = rD.begin();
        const scalar* __restrict__ upperPtr = upper.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();

        const label nFaces = upper.size();
        for (label face=0; face<nFaces; face++)
        {
            rDPtr[uPtr[face]] -= upperPtr[face]*upperPtr[face]/rDPtr[lPtr[face]];
        }

        const label nCells = rD.size();
        for (label cell=0; cell<nCells; cell++)
        {
            rDPtr[cell] = 1.0/rDPtr[cell];
        }
    }

    //- Verbatim DIC apply (OpenFOAM DICPreconditioner.C, precondition),
    //  taking rD explicitly. Identical arithmetic to the member precondition().
    void dicApplyReplica
    (
        solveScalarField& wA,
        const solveScalarField& rA,
        const solveScalarField& rD,
        const scalarField& upper,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        solveScalar* __restrict__ wAPtr = wA.begin();
        const solveScalar* __restrict__ rAPtr = rA.begin();
        const solveScalar* __restrict__ rDPtr = rD.begin();
        const scalar* __restrict__ upperPtr = upper.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();

        const label nCells = wA.size();
        const label nFaces = upper.size();
        const label nFacesM1 = nFaces - 1;

        for (label cell=0; cell<nCells; cell++)
        {
            wAPtr[cell] = rDPtr[cell]*rAPtr[cell];
        }
        for (label face=0; face<nFaces; face++)
        {
            wAPtr[uPtr[face]] -= rDPtr[uPtr[face]]*upperPtr[face]*wAPtr[lPtr[face]];
        }
        for (label face=nFacesM1; face>=0; face--)
        {
            wAPtr[lPtr[face]] -= rDPtr[lPtr[face]]*upperPtr[face]*wAPtr[uPtr[face]];
        }
    }

    //- Verbatim DILU setup (OpenFOAM DILUPreconditioner.C, calcReciprocalD).
    //  OpenFOAM's "ILU" is DILU: no fill, same sparsity as A's lower triangle.
    void diluSetup
    (
        solveScalarField& rD,
        const scalarField& diag,
        const scalarField& upper,
        const scalarField& lower,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        std::copy(diag.begin(), diag.end(), rD.begin());

        solveScalar* __restrict__ rDPtr = rD.begin();
        const scalar* __restrict__ upperPtr = upper.begin();
        const scalar* __restrict__ lowerPtr = lower.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();

        const label nFaces = upper.size();
        for (label face=0; face<nFaces; face++)
        {
            rDPtr[uPtr[face]] -= upperPtr[face]*lowerPtr[face]/rDPtr[lPtr[face]];
        }

        const label nCells = rD.size();
        for (label cell=0; cell<nCells; cell++)
        {
            rDPtr[cell] = 1.0/rDPtr[cell];
        }
    }

    //- Verbatim DILU apply (OpenFOAM DILUPreconditioner.C, precondition).
    void diluApply
    (
        solveScalarField& wA,
        const solveScalarField& rA,
        const solveScalarField& rD,
        const scalarField& upper,
        const scalarField& lower,
        const labelList& uAddr,
        const labelList& lAddr,
        const labelList& losortAddr
    )
    {
        solveScalar* __restrict__ wAPtr = wA.begin();
        const solveScalar* __restrict__ rAPtr = rA.begin();
        const solveScalar* __restrict__ rDPtr = rD.begin();
        const scalar* __restrict__ upperPtr = upper.begin();
        const scalar* __restrict__ lowerPtr = lower.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();
        const label* __restrict__ losortPtr = losortAddr.begin();

        const label nCells = wA.size();
        const label nFaces = upper.size();
        const label nFacesM1 = nFaces - 1;

        for (label cell=0; cell<nCells; cell++)
        {
            wAPtr[cell] = rDPtr[cell]*rAPtr[cell];
        }
        for (label face=0; face<nFaces; face++)
        {
            const label sface = losortPtr[face];
            wAPtr[uPtr[sface]] -=
                rDPtr[uPtr[sface]]*lowerPtr[sface]*wAPtr[lPtr[sface]];
        }
        for (label face=nFacesM1; face>=0; face--)
        {
            wAPtr[lPtr[face]] -=
                rDPtr[lPtr[face]]*upperPtr[face]*wAPtr[uPtr[face]];
        }
    }

    //- Verbatim FDIC setup (OpenFOAM FDICPreconditioner.C constructor).
    //  Costlier than DIC: an extra face loop plus two face-sized arrays, so
    //  it trades MORE setup for LESS apply -- the opposite of what is wanted.
    void fdicSetup
    (
        solveScalarField& rD,
        solveScalarField& rDuUpper,
        solveScalarField& rDlUpper,
        const scalarField& diag,
        const scalarField& upper,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        std::copy(diag.begin(), diag.end(), rD.begin());

        solveScalar* __restrict__ rDPtr = rD.begin();
        solveScalar* __restrict__ rDuUpperPtr = rDuUpper.begin();
        solveScalar* __restrict__ rDlUpperPtr = rDlUpper.begin();
        const scalar* __restrict__ upperPtr = upper.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();

        const label nCells = rD.size();
        const label nFaces = upper.size();

        for (label face=0; face<nFaces; face++)
        {
            rDPtr[uPtr[face]] -= upperPtr[face]*upperPtr[face]/rDPtr[lPtr[face]];
        }
        for (label cell=0; cell<nCells; cell++)
        {
            rDPtr[cell] = 1.0/rDPtr[cell];
        }
        for (label face=0; face<nFaces; face++)
        {
            rDuUpperPtr[face] = rDPtr[uPtr[face]]*upperPtr[face];
            rDlUpperPtr[face] = rDPtr[lPtr[face]]*upperPtr[face];
        }
    }

    //- Verbatim FDIC apply (OpenFOAM FDICPreconditioner.C, precondition).
    void fdicApply
    (
        solveScalarField& wA,
        const solveScalarField& rA,
        const solveScalarField& rD,
        const solveScalarField& rDuUpper,
        const solveScalarField& rDlUpper,
        const labelList& uAddr,
        const labelList& lAddr
    )
    {
        solveScalar* __restrict__ wAPtr = wA.begin();
        const solveScalar* __restrict__ rAPtr = rA.begin();
        const solveScalar* __restrict__ rDPtr = rD.begin();
        const solveScalar* __restrict__ rDuUpperPtr = rDuUpper.begin();
        const solveScalar* __restrict__ rDlUpperPtr = rDlUpper.begin();
        const label* __restrict__ uPtr = uAddr.begin();
        const label* __restrict__ lPtr = lAddr.begin();

        const label nCells = wA.size();
        const label nFaces = uAddr.size();
        const label nFacesM1 = nFaces - 1;

        for (label cell=0; cell<nCells; cell++)
        {
            wAPtr[cell] = rDPtr[cell]*rAPtr[cell];
        }
        for (label face=0; face<nFaces; face++)
        {
            wAPtr[uPtr[face]] -= rDuUpperPtr[face]*wAPtr[lPtr[face]];
        }
        for (label face=nFacesM1; face>=0; face--)
        {
            wAPtr[lPtr[face]] -= rDlUpperPtr[face]*wAPtr[uPtr[face]];
        }
    }
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::DICFrozenPreconditioner::DICFrozenPreconditioner
(
    const lduMatrix::solver& sol,
    const dictionary&
)
:
    lduMatrix::preconditioner(sol),
    rD_(sol.matrix().diag().size()),
    freezeAt_(envLabel("PBR_FREEZE_AT", -1)),
    storeDir_(envString("PBR_STORE", "/root/autodl-tmp/PBR/frozen")),
    fieldTag_(sol.fieldName()),
    reused_(false)
{
    // Time index of the current solve. lduMesh only exposes the registry
    // ("db"), so go through thisDb() -- the same route GAMG uses.
    const label a = sol.matrix().mesh().thisDb().time().timeIndex();

    // Path of the freeze file for this (tag, b) pair
    const fileName freezeFile
    (
        storeDir_ / (fieldTag_ + "_b" + Foam::name(freezeAt_) + ".bin")
    );

    const bool freezeEnabled = (freezeAt_ >= 0);

    if (freezeEnabled && a > freezeAt_)
    {
        // ---- REUSE: load the diagonal frozen at step b ----
        std::ifstream is(freezeFile.c_str(), std::ios::binary);
        if (is.good())
        {
            is.read(reinterpret_cast<char*>(rD_.begin()), rD_.size()*sizeof(solveScalar));
            if (is.gcount() == static_cast<std::streamsize>(rD_.size()*sizeof(solveScalar)))
            {
                reused_ = true;
            }
            else
            {
                FatalErrorInFunction
                    << "Short read of freeze file " << freezeFile
                    << exit(FatalError);
            }
        }
        else
        {
            // Freeze file missing: report loudly rather than silently rebuild,
            // because silent rebuild would corrupt the IT table.
            FatalErrorInFunction
                << "PBR_FREEZE_AT=" << freezeAt_ << " requires freeze file "
                << freezeFile << " at time index " << a
                << ", but it does not exist." << nl
                << "Run the pass that freezes at b first (PBR_FREEZE_AT=" << freezeAt_
                << ", a == b), or clear PBR_FREEZE_AT." << exit(FatalError);
        }
    }
    else
    {
        // ---- REBUILD (or freeze at a == b): compute from current matrix ----
        const scalarField& diag = sol.matrix().diag();
        std::copy(diag.begin(), diag.end(), rD_.begin());
        calcReciprocalD(rD_, sol.matrix());

        if (freezeEnabled && a == freezeAt_)
        {
            // Persist so that all later steps can reuse it.
            std::filesystem::create_directories
            (
                std::string(storeDir_.c_str())
            );
            std::ofstream os(freezeFile.c_str(), std::ios::binary);
            if (!os.good())
            {
                FatalErrorInFunction
                    << "Cannot write freeze file " << freezeFile
                    << exit(FatalError);
            }
            os.write
            (
                reinterpret_cast<const char*>(rD_.begin()),
                rD_.size()*sizeof(solveScalar)
            );
            os.flush();
        }
    }

    // Micro-benchmark (opt-in; has no side effects on rD_)
    benchmark(a);
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

void Foam::DICFrozenPreconditioner::benchmark(const label a) const
{
    if (envLabel("PBR_BENCH", 0) != 1) return;

    // Accept a comma-separated list of time indices: "20,100,250"
    const std::vector<label> benchAt = envLabelList("PBR_BENCH_AT");
    if (std::find(benchAt.begin(), benchAt.end(), a) == benchAt.end()) return;

    // One time index holds several solves (p_rgh, p_rghFinal, and the outer
    // correctors), each constructing its own preconditioner against the same
    // matrix. Benchmark only the first of them per index, so the CSV gets one
    // row per sample point rather than one per solve.
    {
        static std::set<std::pair<label, word>> done;
        if (!done.insert(std::make_pair(a, fieldTag_)).second) return;
    }

    const label reps = envLabel("PBR_BENCH_REPS", 200);
    if (reps <= 1) return;

    const lduMatrix& M = solver_.matrix();
    const scalarField& diag = M.diag();
    const scalarField& upper = M.upper();
    const scalarField& lower = M.hasLower() ? M.lower() : M.upper();
    const labelList& uAddr = M.lduAddr().upperAddr();
    const labelList& lAddr = M.lduAddr().lowerAddr();
    const labelList& losortAddr = M.lduAddr().losortAddr();

    const label nCells = diag.size();
    const label nFaces = upper.size();

    // Which variants to time: "dic", "dilu", "fdic", or "all"
    const string kind = envString("PBR_BENCH_KIND", "all");
    const bool doDic  = (kind == "all" || kind == "dic");
    const bool doDilu = (kind == "all" || kind == "dilu");
    const bool doFdic = (kind == "all" || kind == "fdic");

    // Scratch (deliberately outside the timed regions)
    solveScalarField x(nCells, 1.0);
    solveScalarField wA(nCells, 0.0);
    solveScalarField dicRD(nCells, 0.0);
    solveScalarField diluRD(nCells, 0.0);
    solveScalarField fdicRD(nCells, 0.0);
    solveScalarField fdicRDuUpper(nFaces, 0.0);
    solveScalarField fdicRDlUpper(nFaces, 0.0);

    // One sample per variant: {label, tSetup, tApply}
    struct Sample { const char* tag; double s; double p; };
    std::vector<std::vector<Sample>> samples;

    auto push = [&](int vi, const char* tag, double s, double p)
    {
        if (static_cast<int>(samples.size()) <= vi) samples.resize(vi+1);
        samples[vi].push_back({tag, s, p});
    };
    int viDic = 0, viDilu = 1, viFdic = 2;

    std::vector<double> tAmul;
    tAmul.reserve(reps);

    // Interleaved: any transient load shift hits every variant equally, so the
    // ratios stay meaningful on a shared, noisy machine.
    for (label rep=0; rep<reps; rep++)
    {
        // (0) matrix-vector product (Amul replica) -- shared by all variants
        const double m0 = wallSeconds();
        amulReplica(wA, x, diag, upper, lower, uAddr, lAddr);
        const double m1 = wallSeconds();
        tAmul.push_back(m1 - m0);

        if (doDic)
        {
            const double s0 = wallSeconds();
            dicSetup(dicRD, diag, upper, uAddr, lAddr);
            const double s1 = wallSeconds();
            const double p0 = wallSeconds();
            dicApplyReplica(wA, x, dicRD, upper, uAddr, lAddr);
            const double p1 = wallSeconds();
            push(viDic, "dic", s1 - s0, p1 - p0);
        }
        if (doDilu)
        {
            const double s0 = wallSeconds();
            diluSetup(diluRD, diag, upper, lower, uAddr, lAddr);
            const double s1 = wallSeconds();
            const double p0 = wallSeconds();
            diluApply(wA, x, diluRD, upper, lower, uAddr, lAddr, losortAddr);
            const double p1 = wallSeconds();
            push(viDilu, "dilu", s1 - s0, p1 - p0);
        }
        if (doFdic)
        {
            const double s0 = wallSeconds();
            fdicSetup(fdicRD, fdicRDuUpper, fdicRDlUpper, diag, upper, uAddr, lAddr);
            const double s1 = wallSeconds();
            const double p0 = wallSeconds();
            fdicApply(wA, x, fdicRD, fdicRDuUpper, fdicRDlUpper, uAddr, lAddr);
            const double p1 = wallSeconds();
            push(viFdic, "fdic", s1 - s0, p1 - p0);
        }
    }

    const double ma = median(tAmul);

    // Report per variant. NOTE: every variant is measured against the SAME
    // matrix as the real preconditioner, so a variant's apply time is directly
    // comparable to the others even when PBR_BENCH_KIND narrows the set.
    const string out = envString("PBR_BENCH_OUT", "");
    std::ofstream os;
    if (!out.empty()) os.open(out.c_str(), std::ios::app);

    for (auto& vs : samples)
    {
        if (vs.empty()) continue;
        std::vector<double> s, p;
        s.reserve(vs.size()); p.reserve(vs.size());
        for (auto& v : vs) { s.push_back(v.s); p.push_back(v.p); }
        const double ms = median(s);
        const double mp = median(p);
        const double iter = ma + mp;
        const double r = (iter > 0.0) ? ms/iter : -1.0;

        if (os.good())
        {
            os << a << ',' << fieldTag_ << ',' << vs[0].tag << ','
               << nCells << ',' << nFaces << ',' << reps << ','
               << ms << ',' << ma << ',' << mp << ',' << iter << ',' << r << '\n';
        }
    }
}


void Foam::DICFrozenPreconditioner::calcReciprocalD
(
    solveScalarField& rD,
    const lduMatrix& matrix
)
{
    solveScalar* __restrict__ rDPtr = rD.begin();

    const label* const __restrict__ uPtr = matrix.lduAddr().upperAddr().begin();
    const label* const __restrict__ lPtr = matrix.lduAddr().lowerAddr().begin();
    const scalar* const __restrict__ upperPtr = matrix.upper().begin();

    // Calculate the DIC diagonal
    const label nFaces = matrix.upper().size();
    for (label face=0; face<nFaces; face++)
    {
        rDPtr[uPtr[face]] -= upperPtr[face]*upperPtr[face]/rDPtr[lPtr[face]];
    }

    // Calculate the reciprocal of the preconditioned diagonal
    const label nCells = rD.size();
    for (label cell=0; cell<nCells; cell++)
    {
        rDPtr[cell] = 1.0/rDPtr[cell];
    }
}


void Foam::DICFrozenPreconditioner::precondition
(
    solveScalarField& wA,
    const solveScalarField& rA,
    const direction
) const
{
    solveScalar* __restrict__ wAPtr = wA.begin();
    const solveScalar* __restrict__ rAPtr = rA.begin();
    const solveScalar* __restrict__ rDPtr = rD_.begin();

    const label* const __restrict__ uPtr =
        solver_.matrix().lduAddr().upperAddr().begin();
    const label* const __restrict__ lPtr =
        solver_.matrix().lduAddr().lowerAddr().begin();
    const scalar* const __restrict__ upperPtr =
        solver_.matrix().upper().begin();

    const label nCells = wA.size();
    const label nFaces = solver_.matrix().upper().size();
    const label nFacesM1 = nFaces - 1;

    for (label cell=0; cell<nCells; cell++)
    {
        wAPtr[cell] = rDPtr[cell]*rAPtr[cell];
    }

    for (label face=0; face<nFaces; face++)
    {
        wAPtr[uPtr[face]] -= rDPtr[uPtr[face]]*upperPtr[face]*wAPtr[lPtr[face]];
    }

    for (label face=nFacesM1; face>=0; face--)
    {
        wAPtr[lPtr[face]] -= rDPtr[lPtr[face]]*upperPtr[face]*wAPtr[uPtr[face]];
    }
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// ************************************************************************* //
