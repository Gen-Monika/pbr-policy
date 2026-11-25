/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Description
    PETSc-backed incomplete factorisation preconditioner for lduMatrix.

    See PETScPreconditioner.H for the motivation, what is measured, the
    serial-only caveat, and the environment variables.

\*---------------------------------------------------------------------------*/

#include "PETScPreconditioner.H"

#include "objectRegistry.H"
#include "Time.H"
#include "Pstream.H"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <utility>
#include <set>
#include <vector>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

defineTypeNameAndDebug(PETScPreconditioner, 0);
defineTypeNameAndDebug(PETScICPreconditioner, 0);
defineTypeNameAndDebug(PETScILUPreconditioner, 0);

// ★ Static accumulators for the REAL in-loop apply cost.
//   Static because one preconditioner object is built per solve() (1032x/run).
scalar PETScPreconditioner::s_tApplyAccum_ = 0.0;
label  PETScPreconditioner::s_nApplyCalls_ = 0;

// ★ True totals for buildPC: the CSV is gated to one row per time index,
//   but every solve() builds its own preconditioner.
scalar PETScPreconditioner::s_tSetupAll_ = 0.0;
label  PETScPreconditioner::s_nBuildPC_  = 0;

lduMatrix::preconditioner::
    addsymMatrixConstructorToTable<PETScICPreconditioner>
    addPETScICPreconditionerSymMatrixConstructorToTable_;

lduMatrix::preconditioner::
    addasymMatrixConstructorToTable<PETScICPreconditioner>
    addPETScICPreconditionerAsymMatrixConstructorToTable_;

lduMatrix::preconditioner::
    addsymMatrixConstructorToTable<PETScILUPreconditioner>
    addPETScILUPreconditionerSymMatrixConstructorToTable_;

lduMatrix::preconditioner::
    addasymMatrixConstructorToTable<PETScILUPreconditioner>
    addPETScILUPreconditionerAsymMatrixConstructorToTable_;


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace
{
    // D0: only output naming changes. Serial paths and all policy/PC arithmetic
    // are unchanged; MPI ranks write their own traces instead of interleaving.
    string rankLogPath(const string& path)
    {
        if (path.empty() || !Pstream::parRun())
        {
            return path;
        }
        // Build via std::string then construct Foam::string explicitly: the
        // ternary would mix std::string (operator+ result) with Foam::string.
        return string(std::string(path) + ".r" + Foam::name(Pstream::myProcNo()));
    }

    label envLabel(const char* name, const label fallback)
    {
        const char* s = std::getenv(name);
        if (!s || !*s) return fallback;
        return static_cast<label>(std::strtol(s, nullptr, 10));
    }

    string envString(const char* name, const char* fallback)
    {
        const char* s = std::getenv(name);
        return string((s && *s) ? s : fallback);
    }

    //- Floating-point env lookup (heuristic thresholds, 2026-10-13)
    scalar envScalar(const char* name, const scalar fallback)
    {
        const char* s = std::getenv(name);
        if (!s || !*s) return fallback;
        return static_cast<scalar>(std::strtod(s, nullptr));
    }

    double wallSeconds()
    {
        using namespace std::chrono;
        return duration<double>(steady_clock::now().time_since_epoch()).count();
    }

    double medianOf(std::vector<double> v)
    {
        if (v.empty()) return 0.0;
        std::sort(v.begin(), v.end());
        const std::size_t n = v.size();
        return (n % 2) ? v[n/2] : 0.5*(v[n/2 - 1] + v[n/2]);
    }

    //- A persistent PC carried across time steps, per field.
    //  PETSc's own PCSetReusePreconditioner() decides whether PCSetUp is
    //  allowed to re-factor. Verified in isolation (reuse_test.cpp):
    //  re-pointing a PC at a new matrix with reuse=TRUE leaves PCApply output
    //  bit-identical to the old factor, i.e. the factorisation is genuinely
    //  NOT recomputed. That is what makes "reuse" cheap; without it the reuse
    //  path pays the full factorisation and no policy can save anything.
    struct PersistentPC
    {
        PC  pc;
        Mat A;          // matrix the PC is currently pointed at
        Vec x, y;       // persistent work vectors
        bool factored;  // whether pc currently holds a valid factor
        PersistentPC() : pc(nullptr), A(nullptr), x(nullptr), y(nullptr),
                         factored(false) {}
    };

    std::map<word, PersistentPC>& pcCache()
    {
        static std::map<word, PersistentPC> cache;
        return cache;
    }

    //- ★ A2 (v2, 2026-10-12): state of the ONLINE rebuild policy, per field.
    //
    //  This is a LINE-BY-LINE port of sim_online() in online_holdout_v2.py
    //  (variant P0 / T0: no probing), which is the policy validated offline
    //  in A1c. v1 of this port had three discrepancies, all of which lengthen
    //  the rebuild period, and all are fixed here:
    //    (1) dN was keyed by the post-decision age but queried with the
    //        pre-decision age, so every query returned the increment of an age
    //        ONE YEAR YOUNGER -> systematic under-estimate -> drift to 4-5;
    //    (2) the last warm-up rebuild (r + N) was folded into the first
    //        averaging window -- the very bug A1c fixed offline;
    //    (3) the accn==0 fallback used lvl instead of tot/(t-1).
    //
    //  Ages are REAL ages: a step that reuses the factor built at step b runs
    //  at age t - b >= 1; a step that rebuilds runs at age 0.
    //
    //  Granularity: the preconditioner object is re-constructed for every
    //  SOLVE (s per step), so the state is static and keyed by field; the
    //  decision is taken once per STEP, at its first solve, after folding the
    //  completed step into the statistics. Hence strictly causal.
    //
    //  Units: N = applies summed over the step's solves (== sum of CG
    //  iterations, the offline N_step). Rebuild cost charged per rebuild step:
    //      PBR_PETSC_ONLINE_RCOST=solve : r          (offline A1c convention)
    //      PBR_PETSC_ONLINE_RCOST=step  : r x (factorisations done that step)
    //  Measured 2026-10-12: every rebuild step performs s=3 factorisations
    //  (one per pressure solve), so "solve" under-charges a rebuild by 3x.
    struct OnlineState
    {
        label lastStep;        // time index of the step being accumulated
        label nSolveInStep;    // solves already seen in lastStep
        label stepApplies;     // applies accumulated in lastStep
        label stepFact;        // factorisations performed in lastStep
        label runAge;          // age lastStep runs at (0 = rebuilt)
        label heldBase;        // step at which the held factor was built
        label nDone;           // completed (folded) steps

        // fold diagnostics of the previous step (for the log / replay test)
        label prevN, prevFact, prevAge;
        scalar prevRcost;

        std::vector<scalar> levels;                    // N at rebuild steps
        std::map<label, std::vector<scalar> > dN;      // real age -> N - med(levels)
        scalar acc; label accn;                        // current-cycle window
        scalar tot;                                    // total cost so far
        std::vector<scalar> rSamples;                  // measured r per factorisation

        label decision;        // >0 rebuild at that step; <0 reuse base |v|
        scalar est, avg;
        string dSrc;           // how delta was obtained: hit/flat/extrap/zero/none

        OnlineState()
        :
            lastStep(-1), nSolveInStep(0), stepApplies(0), stepFact(0),
            runAge(0), heldBase(-1), nDone(0),
            prevN(0), prevFact(0), prevAge(0), prevRcost(0.0),
            acc(0.0), accn(0), tot(0.0),
            decision(0), est(0.0), avg(0.0), dSrc("none")
        {}
    };

    std::map<word, OnlineState>& onlineCache()
    {
        static std::map<word, OnlineState> cache;
        return cache;
    }

    //- Median of a copy (the sample lists are small: at most a few hundred
    //  entries per age, so an O(n log n) copy per decision is irrelevant next
    //  to a PETSc factorisation).
    scalar medianCopy(std::vector<scalar> v)
    {
        if (v.empty()) return 0.0;
        std::sort(v.begin(), v.end());
        const std::size_t n = v.size();
        return (n % 2) ? v[n/2] : 0.5*(v[n/2 - 1] + v[n/2]);
    }

    //- Sorted list of ages that actually hold samples
    std::vector<label> agesWithSamples
    (
        const std::map<label, std::vector<scalar> >& dN
    )
    {
        std::vector<label> ks;
        for
        (
            std::map<label, std::vector<scalar> >::const_iterator it = dN.begin();
            it != dN.end();
            ++it
        )
        {
            if (!it->second.empty()) ks.push_back(it->first);
        }
        return ks;
    }

    //- Verbatim internal part of lduMatrix::Amul (serial mesh)
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

        for (label c=0; c<nCells; c++) w[c] = d[c]*p[c];
        for (label f=0; f<nFaces; f++)
        {
            w[u[f]] += lo[f]*p[l[f]];
            w[l[f]] += up[f]*p[u[f]];
        }
    }
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::PETScPreconditioner::PETScPreconditioner
(
    const lduMatrix::solver& sol,
    const dictionary& solverControls,
    const char* defaultKind
)
:
    lduMatrix::preconditioner(sol),
    A_(nullptr),
    pc_(nullptr),
    kind_(envString("PBR_PETSC_KIND", defaultKind)),
    levels_(envLabel("PBR_PETSC_LEVELS", 0)),
    x_(nullptr),
    y_(nullptr),
    valid_(false),
    tConvert_(0),
    tPCSetup_(0),
    timing_(envLabel("PBR_PETSC_BENCH", 0) == 1),
    reps_(envLabel("PBR_PETSC_REPS", 50)),
    outPath_(rankLogPath(envString("PBR_PETSC_OUT", ""))),
    timeIndex_(0),
    fieldTag_(sol.fieldName()),
    freezeAt_(envLabel("PBR_PETSC_FREEZE_AT", -1)),
    storeDir_(envString("PBR_PETSC_STORE", "/tmp/pbr_petsc_frozen")),
    reusedFrom_(-1),
    tFreeze_(0),
    tAssemble_(0),
    period_(envLabel("PBR_PETSC_FREEZE_K", -1)),
    freezeBase_(envLabel("PBR_PETSC_FREEZE_BASE", 100)),
    adopted_(false),
    online_(envLabel("PBR_PETSC_ONLINE", 0) == 1),
    onlineBase_(envLabel("PBR_PETSC_ONLINE_BASE", 100))
{
    // --- PETSc must be initialised before any PETSc call ---
    PetscBool isInit = PETSC_FALSE;
    PetscInitialized(&isInit);
    if (isInit != PETSC_TRUE)
    {
        // OpenFOAM's argv is not available here, and PETSc's argv form needs a
        // char** lvalue. PetscInitializeNoArguments() is the sanctioned way to
        // initialise without one (petscsys.h).
        PetscInitializeNoArguments();
    }

    const lduMatrix& M = sol.matrix();

    timeIndex_ = M.mesh().thisDb().time().timeIndex();

    // ---- ★ A2: ONLINE policy takes precedence over every fixed schedule ----
    if (online_)
    {
        onlineDecide();
    }
    // ---- Snapshot generation pass (rebuild every step, write every step) ----
    else if (period_ >= 0 && freezeAt_ < 0)
    {
        freezeAt_ = timeIndex_;      // write a snapshot for this step
        reusedFrom_ = -1;            // always rebuild
    }
    else if (period_ >= 0 && freezeAt_ >= 0)
    {
        // ---- Periodic policy: rebuild every `period_` steps, starting from b0 ----
        const label b0 = freezeBase_;
        if (timeIndex_ >= b0)
        {
            const label k = (timeIndex_ - b0)/period_;
            const label b = b0 + k*period_;          // base step governing this step
            if (timeIndex_ > b)
            {
                reusedFrom_ = b;                     // reuse the base's snapshot
                freezeAt_ = -1;                      // do not overwrite it
            }
            else
            {
                freezeAt_ = b;                       // this step IS a base: rebuild + snapshot
                reusedFrom_ = -1;
            }
        }
        else
        {
            freezeAt_ = -1;
            reusedFrom_ = -1;
        }
    }
    else
    {
        // ---- Single-point freeze (original behaviour) ----
        if (freezeAt_ >= 0 && timeIndex_ > freezeAt_)
        {
            reusedFrom_ = freezeAt_;
        }
    }

    // ---- Assemble timing: buildPETScMatrix() was previously OUTSIDE every
    //      timer, which made the wall-clock saving exceed the model's
    //      prediction. Time it explicitly so the budget closes.
    const double ca0 = wallSeconds();
    buildPETScMatrix(M);
    const double ca1 = wallSeconds();
    tAssemble_ = ca1 - ca0;

    buildPC();

    // ★ Every solve() gets its own preconditioner instance, so buildPC() runs
    //   once per SOLVE (1032x per run), not once per time step. The CSV row
    //   is written under a "first solve per time index" gate, so the per-row
    //   tPCSetup covers only 1 of the 3 solves. Accumulate the true total.
    s_tSetupAll_ += tPCSetup_;
    s_nBuildPC_++;

    // Report without perturbing the solver
    report(M);
}


// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

Foam::PETScPreconditioner::~PETScPreconditioner()
{
    // The PC, the Mat and the work vectors all belong to the persistent cache
    // (pcCache()). They must survive this instance so that the factorisation
    // built at step b is still available at steps a > b. Only A_ is owned
    // here when it was relayed and immediately handed to PCSetOperators --
    // PETSc increments its reference count, so destroying our handle is safe.
    if (!adopted_)
    {
        if (A_) MatDestroy(&A_);
    }
}

// * * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// * * * * * * * * * * * * * * * *  A2: the online policy  * * * * * * * * * * * * * * * * * * * * * * * * * * //

void Foam::PETScPreconditioner::onlineNoteApply() const
{
    // One CG preconditioner application of the current step.
    if (!online_ || inReport_) return;
    onlineCache()[fieldTag_].stepApplies++;
}


void Foam::PETScPreconditioner::onlineDecide()
{
    OnlineState& S = onlineCache()[fieldTag_];

    static const string rcostMode = envString("PBR_PETSC_ONLINE_RCOST", "solve");
    static const string lvlMode   = envString("PBR_PETSC_ONLINE_LVL",   "last");

    // ★ A-diag fix (2026-10-12): delta estimation policy for UNSEEN ages.
    //
    //   Symptom it fixes (l15 / a2A_ONLs): the policy settles into a strict
    //   period-2 cycle -- rebuild, reuse, rebuild, reuse -- and never escapes.
    //   Root cause chain:
    //     (a) the first few reuses right after the warmup hit a strong
    //         TRANSIENT (N jumps 16 -> 140 -> 169), and those samples land in
    //         dN[1], dN[2];
    //     (b) at age 2 the linear EXTRAPOLATION from dN[1],dN[2] produces a
    //         huge delta (~182), which exceeds avg (~155) and forces a rebuild;
    //     (c) because age 2 is ALWAYS rebuilt, dN[2] never gains a second
    //         sample, so the bad estimate can never be corrected -- the
    //         policy is self-locked by a single sample.
    //
    //   "extrap" keeps the old behaviour (regression-safe default).
    //   "flat"   uses the median at the largest age that actually has samples
    //            and holds it constant -- no invented slope. Measured effect:
    //            l15 18.83% -> 2.96% regret, other configs unchanged.
    //   "zero"   treats an unseen age as no degradation (delta = 0).
    //            NOTE: measured to be catastrophic -- it suppresses rebuilds
    //            until iteration counts explode (6000%+ regret). Kept only
    //            because it documents the failure mode.
    static const string dMode = envString("PBR_PETSC_ONLINE_DMODE", "extrap");

    // ★ Minimum sample count before dN[a] is trusted. Default 1 preserves the
    //   historical behaviour exactly; raising it makes the estimator refuse a
    //   single-sample age and fall back to the flat rule instead.
    static const label dMinN = envLabel("PBR_PETSC_ONLINE_DMINN", 1);

    const label b0 = onlineBase_;

    if (timeIndex_ != S.lastStep)
    {
        const scalar rMed = medianCopy(S.rSamples);

        // ---- 1) fold the COMPLETED step (mirrors the offline per-step update)
        if (S.lastStep >= 0 && S.nSolveInStep > 0)
        {
            const scalar N = static_cast<scalar>(S.stepApplies);
            S.prevN = S.stepApplies;
            S.prevFact = S.stepFact;
            S.prevAge = S.runAge;
            S.prevRcost = 0.0;

            if (S.runAge == 0)
            {
                const scalar rc =
                    (rcostMode == "step")
                  ? rMed*static_cast<scalar>(S.stepFact)
                  : rMed;
                S.prevRcost = rc;
                const scalar c = rc + N;
                S.tot += c;
                S.levels.push_back(N);
                if (S.lastStep < b0) { S.acc = 0.0; S.accn = 0; }   // A1c fix
                else                 { S.acc = c;   S.accn = 1; }
            }
            else
            {
                S.tot += N;
                if (!S.levels.empty())
                {
                    const scalar bmed = medianCopy(S.levels);
                    if (bmed > 1e-9) S.dN[S.runAge].push_back(N - bmed);
                }
                S.acc += N;
                S.accn += 1;
            }
            S.nDone++;
        }

        S.lastStep = timeIndex_;
        S.nSolveInStep = 0;
        S.stepApplies = 0;
        S.stepFact = 0;

        // ---- 2) decide THIS step (offline: sim_online, P0/T0)
        bool rebuild = true;
        S.est = 0.0; S.avg = 0.0;

        // ====================================================================
        // ★ 启发式对照规则（2026-10-13）
        //   PBR_PETSC_ONLINE_POLICY = online | chalmers | reac | ratio
        //
        //   目的：把 §7.5 的启发式对照从"表上评估"升级为"C++ 实测"。
        //
        //   ★★ 因果性与口径（必须与离线模型一致）：
        //     三条规则都只用【刚完成那一步】的迭代数 S.prevN 做判断，
        //     再在【本步】重建。这与生产求解器的实际行为一致
        //     （迭代数要算完才知道），也与 Stage D 离线脚本的用法对应。
        //
        //     chalmers: N_prev > max(2·k0, 10)          k0 = 上次重建步的 N
        //     reac    : N_prev > reac                   reac 为整数阈值
        //     ratio   : (N_prev − k0)/k0 > frac         frac 为相对阈值
        // ====================================================================
        static const string policy = envString("PBR_PETSC_ONLINE_POLICY", "online");
        static const label hReac  = envLabel("PBR_PETSC_ONLINE_REAC", 120);
        static const scalar hFrac = envScalar("PBR_PETSC_ONLINE_FRAC", 0.20);
        static const scalar hFact = envScalar("PBR_PETSC_ONLINE_FACTOR", 2.0);
        static const scalar hFloor= envScalar("PBR_PETSC_ONLINE_FLOOR", 10.0);

        if (policy != "online")
        {
            if (!(timeIndex_ >= b0 && S.heldBase >= 0 && !S.levels.empty()))
            {
                rebuild = true;                       // 预热期一律重建
            }
            else
            {
                const scalar k0 = S.levels.back();    // 上次重建步的 N
                const scalar np = S.prevN;            // 刚完成那一步的 N
                if (policy == "chalmers")
                {
                    const scalar thr = std::max(hFact*k0, hFloor);
                    rebuild = (np > thr);
                    S.est = np; S.avg = thr;
                }
                else if (policy == "reac")
                {
                    rebuild = (np > static_cast<scalar>(hReac));
                    S.est = np; S.avg = static_cast<scalar>(hReac);
                }
                else if (policy == "ratio")
                {
                    rebuild = (k0 > 1e-9) && ((np - k0)/k0 > hFrac);
                    S.est = (k0 > 1e-9) ? (np - k0)/k0 : 0.0; S.avg = hFrac;
                }
                else
                {
                    rebuild = true;
                }
                S.dSrc = policy;
            }

            if (rebuild)
            {
                S.decision = timeIndex_;
                S.heldBase = timeIndex_;
                S.runAge = 0;
            }
            else
            {
                S.decision = -S.heldBase;
                S.runAge = timeIndex_ - S.heldBase;
            }
            onlineLog();
        }
        else if (timeIndex_ >= b0 && S.heldBase >= 0 && !S.levels.empty())
        {
            const label a = timeIndex_ - S.heldBase;    // real age if reused

            scalar lvl = S.levels.back();
            if (lvlMode == "trend" && S.levels.size() >= 2)
            {
                const std::size_t n = S.levels.size();
                lvl = S.levels[n-1] + (S.levels[n-1] - S.levels[n-2]);
            }

            const scalar avg =
                (S.accn > 0)
              ? S.acc/static_cast<scalar>(S.accn)
              : S.tot/static_cast<scalar>(std::max<label>(1, S.nDone));

            scalar delta = 0.0;
            string dSrc = "none";
            std::map<label, std::vector<scalar> >::iterator hit = S.dN.find(a);
            if (hit != S.dN.end()
                && static_cast<label>(hit->second.size()) >= dMinN)
            {
                delta = medianCopy(hit->second);
                dSrc = "hit";
            }
            else
            {
                // Ages that actually have (enough) samples, ascending.
                // ★ dMinN gates out single-sample ages (the l15 self-lock was
                //   driven by exactly one polluted sample at age 2).
                //   Note: use find(), never operator[] -- a non-const map
                //   lookup with [] would default-insert on a missing key.
                std::vector<label> ks0 = agesWithSamples(S.dN);
                std::vector<label> ks;
                for (std::size_t q = 0; q < ks0.size(); ++q)
                {
                    std::map<label, std::vector<scalar> >::const_iterator f =
                        S.dN.find(ks0[q]);
                    if (f != S.dN.end()
                        && static_cast<label>(f->second.size()) >= dMinN)
                    {
                        ks.push_back(ks0[q]);
                    }
                }

                if (dMode == "zero")
                {
                    // Unseen age => assume no degradation (delta stays 0).
                    dSrc = "zero";
                }
                else if (!ks.empty()
                      && (dMode == "flat" || ks.size() < 2))
                {
                    // Hold the largest sampled age's median constant.
                    delta = medianCopy(S.dN[ks[ks.size()-1]]);
                    dSrc = "flat";
                }
                else if (ks.size() >= 2)
                {
                    const label a2 = ks[ks.size()-1], a1 = ks[ks.size()-2];
                    const scalar d2 = medianCopy(S.dN[a2]);
                    const scalar d1 = medianCopy(S.dN[a1]);
                    const scalar sl = (d2 - d1)/std::max<scalar>(1e-9, a2 - a1);
                    delta = d2 + sl*static_cast<scalar>(a - a2);
                    dSrc = "extrap";
                }
                else
                {
                    // ★ BOOTSTRAP FALLBACK (2026-10-12, found in smoke test).
                    //
                    //   ks is empty because EVERY age has fewer than dMinN
                    //   samples. Without this branch delta stays 0, so
                    //   est = lvl < avg forever => never rebuild => no new
                    //   samples ever accumulate => the counter can never reach
                    //   dMinN. Measured: ONLf with DMINN=3 deadlocked at
                    //   runAge=245, est=15.0, avg=12114, 0 post-warmup
                    //   rebuilds, and ran ~30x slower than ONLs.
                    //
                    //   So dMinN must only express PREFERENCE to the
                    //   extrapolation, never remove the policy's ability to
                    //   decide. Fall back to the largest age that has ANY
                    //   sample (the pre-dMinN behaviour for this case).
                    std::vector<label> ksAny = agesWithSamples(S.dN);
                    if (!ksAny.empty())
                    {
                        delta = medianCopy(S.dN[ksAny[ksAny.size()-1]]);
                        dSrc = "flat_boot";
                    }
                    else
                    {
                        dSrc = "boot_none";
                    }
                }
            }

            const scalar est = lvl + std::max<scalar>(0.0, delta);
            S.est = est;
            S.avg = avg;
            rebuild = (est > avg);
            S.dSrc = dSrc;

            if (!rebuild)
            {
                S.decision = -S.heldBase;
                S.runAge = a;
            }
        }

        if (rebuild)
        {
            S.decision = timeIndex_;
            S.heldBase = timeIndex_;
            S.runAge = 0;
        }

        onlineLog();
    }

    // ---- 3) every solve of the step follows the step decision
    if (S.decision > 0) { freezeAt_ = S.decision; reusedFrom_ = -1; }
    else                { freezeAt_ = -1;         reusedFrom_ = -S.decision; }

    S.nSolveInStep++;
}


void Foam::PETScPreconditioner::onlineLog() const
{
    static const string path = rankLogPath(envString("PBR_PETSC_ONLINE_OUT", ""));
    if (path.empty()) return;

    std::ofstream os(path.c_str(), std::ios::app);
    if (!os.good()) return;

    static bool header = false;
    if (!header)
    {
        header = true;
        // prev* describe the step folded just before this decision, so a
        // replay can re-derive every decision from the log alone.
        // dSrc records WHICH branch produced delta (hit/flat/extrap/zero/none)
        // -- added 2026-10-12 to diagnose the l15 period-2 deadlock.
        os << "timeIndex,rebuild,reusedFrom,runAge,est,avg,rMed,"
              "prevN,prevFact,prevAge,prevRcost,dm\n";
    }

    const OnlineState& S = onlineCache()[fieldTag_];
    os  << timeIndex_ << ','
        << ((S.decision > 0) ? 1 : 0) << ','
        << ((S.decision > 0) ? -1 : -S.decision) << ','
        << S.runAge << ','
        << S.est << ',' << S.avg << ','
        << medianCopy(S.rSamples) << ','
        << S.prevN << ',' << S.prevFact << ',' << S.prevAge << ','
        << S.prevRcost << ',' << S.dSrc << '\n';
}


void Foam::PETScPreconditioner::buildPETScMatrix(const lduMatrix& M)
{
    const double c0 = wallSeconds();

    const label nCells = M.diag().size();
    const label nFaces = M.upper().size();

    const scalarField& diagNow  = M.diag();
    const scalarField& upperNow = M.upper();
    const scalarField& lowerNow = M.hasLower() ? M.lower() : M.upper();

    // Connectivity never changes for a fixed mesh; take it from the current matrix
    const labelList& uAddr = M.lduAddr().upperAddr();
    const labelList& lAddr = M.lduAddr().lowerAddr();

    // Coefficients: either the current matrix, or a frozen snapshot from step b
    scalarField diagOwn, upperOwn, lowerOwn;
    const scalarField* diagP  = &diagNow;
    const scalarField* upperP = &upperNow;
    const scalarField* lowerP = &lowerNow;

    if (reusedFrom_ >= 0)
    {
        // ---- REUSE: read the snapshot taken at step b ----
        const fileName ff(storeDir_ / (fieldTag_ + "_petb" + Foam::name(reusedFrom_) + ".bin"));

        std::ifstream is(ff.c_str(), std::ios::binary);
        if (!is.good())
        {
            FatalErrorInFunction
                << "PBR_PETSC_FREEZE_AT=" << freezeAt_ << " requires snapshot "
                << ff << " at time index " << timeIndex_ << ", but it is missing."
                << nl << "Run the pass that freezes at b first, or clear the variable."
                << exit(FatalError);
        }

        diagOwn.resize(nCells);
        upperOwn.resize(nFaces);
        lowerOwn.resize(nFaces);

        const std::streamsize nb = sizeof(scalar);
        is.read(reinterpret_cast<char*>(diagOwn.begin()),  nCells*nb);
        is.read(reinterpret_cast<char*>(upperOwn.begin()), nFaces*nb);
        is.read(reinterpret_cast<char*>(lowerOwn.begin()), nFaces*nb);

        if (!is)
        {
            FatalErrorInFunction
                << "Short read of snapshot " << ff << exit(FatalError);
        }

        diagP = &diagOwn; upperP = &upperOwn; lowerP = &lowerOwn;

        tFreeze_ = wallSeconds() - c0;
    }
    else if (freezeAt_ >= 0 && timeIndex_ == freezeAt_)
    {
        // ---- FREEZE: write the current coefficients for later reuse ----
        std::filesystem::create_directories(std::string(storeDir_.c_str()));

        const fileName ff(storeDir_ / (fieldTag_ + "_petb" + Foam::name(freezeAt_) + ".bin"));

        std::ofstream os(ff.c_str(), std::ios::binary);
        if (!os.good())
        {
            FatalErrorInFunction << "Cannot write snapshot " << ff << exit(FatalError);
        }
        const std::streamsize nb = sizeof(scalar);
        os.write(reinterpret_cast<const char*>(diagNow.begin()),  nCells*nb);
        os.write(reinterpret_cast<const char*>(upperNow.begin()), nFaces*nb);
        os.write(reinterpret_cast<const char*>(lowerNow.begin()), nFaces*nb);
        os.flush();

        tFreeze_ = wallSeconds() - c0;
    }

    const scalarField& diag  = *diagP;
    const scalarField& upper = *upperP;
    const scalarField& lower = *lowerP;

    // Preallocate: diagonal plus one entry per face in each direction.
    // Symmetric matrices may repeat a (row,col) pair; MatSetValuesOption with
    // ADD_VALUES would then sum duplicates, which is what the lduMatrix
    // semantics require, so INSERT_VALUES is replaced by ADD_VALUES and the
    // matrix is zeroed first.
    MatCreate(PETSC_COMM_SELF, &A_);
    MatSetSizes(A_, nCells, nCells, nCells, nCells);
    MatSetType(A_, MATAIJ);
    MatSeqAIJSetPreallocation(A_, nFaces > 0 ? 8 : 1, nullptr);

    for (label c = 0; c < nCells; c++)
    {
        MatSetValue(A_, c, c, diag[c], ADD_VALUES);
    }
    for (label f = 0; f < nFaces; f++)
    {
        // Matches lduMatrix::Amul exactly:
        //   Apsi[u] += lower[f]*psi[l]
        //   Apsi[l] += upper[f]*psi[u]
        MatSetValue(A_, uAddr[f], lAddr[f], lower[f], ADD_VALUES);
        MatSetValue(A_, lAddr[f], uAddr[f], upper[f], ADD_VALUES);
    }
    MatAssemblyBegin(A_, MAT_FINAL_ASSEMBLY);
    MatAssemblyEnd(A_, MAT_FINAL_ASSEMBLY);

    tConvert_ = wallSeconds() - c0 - tFreeze_;
}


void Foam::PETScPreconditioner::buildPC()
{
    const double c0 = wallSeconds();

    PersistentPC& P = pcCache()[fieldTag_];

    // First time we see this field: create the PC and its work vectors
    if (!P.pc)
    {
        PCCreate(PETSC_COMM_SELF, &P.pc);
        if (kind_ == "ilu") PCSetType(P.pc, PCILU);
        else                PCSetType(P.pc, PCICC);
        if (levels_ > 0)    PCFactorSetLevels(P.pc, static_cast<PetscInt>(levels_));
    }

    // Persistent work vectors sized for this matrix
    if (!P.x) MatCreateVecs(A_, &P.x, &P.y);

    // Re-point the PC at the matrix we just relayed
    PCSetOperators(P.pc, A_, A_);

    // ---- the decision: may PCSetUp re-factor? ----
    // PCSetReusePreconditioner(pc, PETSC_TRUE)  => KEEP the existing factor
    // PCSetReusePreconditioner(pc, PETSC_FALSE) => allow PCSetUp to re-factor
    // So the flag is TRUE exactly when we are REUSING a factor built earlier.
    const PetscBool reusing = (reusedFrom_ >= 0) ? PETSC_TRUE : PETSC_FALSE;
    PCSetReusePreconditioner(P.pc, reusing);

    PCSetUp(P.pc);

    // ★ A2: count factorisations of the current step (for RCOST=step)
    if (online_ && !reusing) onlineCache()[fieldTag_].stepFact++;

    // ---- ★ Fill-saturation probe (PBR_PETSC_NNZ=1) ----
    //   r's per-level increment fell from +3.99 (15) to +2.49 (20) while tIter
    //   did not move at all. That pattern says the factorisation has filled the
    //   matrix rather than that the method is merely flattening. Measure the
    //   nonzero count of the FACTORED matrix and compare it with nRows^2: if
    //   nz_used/n^2 is approaching 1, there is simply no sparsity left for
    //   further fill levels to exploit. Printed once per process.
    {
        static const bool wantNnz = (std::getenv("PBR_PETSC_NNZ") != nullptr);
        if (wantNnz && !reusing)
        {
            static bool done = false;
            if (!done)
            {
                done = true;
                Mat F = nullptr;
                PCFactorGetMatrix(P.pc, &F);
                if (F)
                {
                    MatInfo info;
                    MatGetInfo(F, MAT_LOCAL, &info);
                    PetscInt nr = 0, nc = 0;
                    MatGetSize(F, &nr, &nc);
                    const double dense = static_cast<double>(nr)*nc;
                    const double ratio = dense > 0.0 ? info.nz_used/dense : -1.0;
                    Info<< "PBR_NNZ levels=" << levels_
                        << " n=" << nr
                        << " nz_used=" << static_cast<label>(info.nz_used)
                        << " nz_alloc=" << static_cast<label>(info.nz_allocated)
                        << " dense_nnz=" << static_cast<label>(dense)
                        << " fillRatio=" << ratio
                        << " (nz_used/nnzA)"
                        << endl;
                }
            }
        }
    }

    pc_ = P.pc;
    x_  = P.x;
    y_  = P.y;
    valid_ = true;
    adopted_ = true;

    tPCSetup_ = wallSeconds() - c0;
}

void Foam::PETScPreconditioner::precondition
(
    solveScalarField& wA,
    const solveScalarField& rA,
    const direction
) const
{
    if (!valid_)
    {
        FatalErrorInFunction
            << "PETSc preconditioner was not set up successfully"
            << exit(FatalError);
    }

    // ★ Time the REAL in-loop apply. report() does 8 isolated repetitions
    //   after this, guarded by inReport_, so they do not pollute the total.
    const double ct0 = wallSeconds();

    const label nCells = wA.size();

    PetscInt vn = 0;
    VecGetSize(x_, &vn);
    if (static_cast<label>(vn) != nCells)
    {
        FatalErrorInFunction
            << "Vector size " << vn << " does not match field size " << nCells
            << exit(FatalError);
    }

    // Copy residual into the PETSc vector (PetscScalar is double here)
    PetscScalar* xarr = nullptr;
    VecGetArray(x_, &xarr);
    for (label c = 0; c < nCells; c++)
    {
        xarr[c] = static_cast<PetscScalar>(rA[c]);
    }
    VecRestoreArray(x_, &xarr);

    PCApply(pc_, x_, y_);

    const PetscScalar* yarr = nullptr;
    VecGetArrayRead(y_, &yarr);
    for (label c = 0; c < nCells; c++)
    {
        wA[c] = static_cast<solveScalar>(yarr[c]);
    }
    VecRestoreArrayRead(y_, &yarr);

    // ★ Accumulate the in-loop apply cost (excluded during report())
    if (!inReport_)
    {
        s_tApplyAccum_ += wallSeconds() - ct0;
        s_nApplyCalls_++;
    }

    // ★ A2: charge this applied solve to the online policy
    onlineNoteApply();
}


void Foam::PETScPreconditioner::report(const lduMatrix& M) const
{
    if (!timing_) return;

    // ---- self-check: does the PETSc Mat reproduce lduMatrix::Amul? ----
    if (envLabel("PBR_PETSC_CHECK", 0) == 1)
    {
        const label n = M.diag().size();

        // Deterministic non-trivial vector
        solveScalarField x(n, 0.0);
        for (label c = 0; c < n; c++)
        {
            x[c] = std::sin(0.7*scalar(c)) + 0.3*std::cos(0.11*scalar(c));
        }

        // OpenFOAM reference product
        solveScalarField wOF(n, 0.0);
        amulReplica
        (
            wOF, x,
            M.diag(), M.upper(),
            M.hasLower() ? M.lower() : M.upper(),
            M.lduAddr().upperAddr(), M.lduAddr().lowerAddr()
        );

        // PETSc product
        Vec xv, yv;
        MatCreateVecs(A_, &xv, &yv);
        PetscScalar* xa = nullptr;
        VecGetArray(xv, &xa);
        for (label c = 0; c < n; c++) xa[c] = static_cast<PetscScalar>(x[c]);
        VecRestoreArray(xv, &xa);
        MatMult(A_, xv, yv);
        const PetscScalar* ya = nullptr;
        VecGetArrayRead(yv, &ya);

        scalar num = 0, den = 0, maxAbs = 0;
        for (label c = 0; c < n; c++)
        {
            const scalar d = std::fabs(scalar(ya[c]) - wOF[c]);
            num += d*d;
            den += wOF[c]*wOF[c];
            maxAbs = max(maxAbs, d);
        }
        VecRestoreArrayRead(yv, &ya);
        VecDestroy(&xv); VecDestroy(&yv);

        const scalar relErr = (den > 0) ? std::sqrt(num/den) : -1;

        // PETSc precision / scalar size, to rule out a precision mismatch
        size_t sz = 0;
        PetscDataTypeGetSize(PETSC_SCALAR, &sz);

        Info<< "PETSC-CHECK: n=" << n
            << " sizeof(PetscScalar)=" << sz
            << " MatMult-vs-Amul relErr=" << relErr
            << " maxAbsDiff=" << maxAbs
            << endl;

        // ---- which preconditioner actually helps on THIS matrix? ----
        // DIC and IC(0) are both zero-fill incomplete Cholesky, so their CG
        // iteration counts should be comparable. A large gap means the PETSc
        // factorisation is behaving differently (e.g. a shift, or a breakdown
        // on a semi-definite pressure matrix).
        {
            Vec bv, xv2;
            MatCreateVecs(A_, &bv, &xv2);
            VecSet(bv, 1.0);

            const char* pcs[] = {"none", "icc", "ilu", "jacobi"};
            for (int i = 0; i < 4; i++)
            {
                KSP ksp;
                KSPCreate(PETSC_COMM_SELF, &ksp);
                KSPSetOperators(ksp, A_, A_);
                KSPSetType(ksp, KSPCG);
                PC kpc;
                KSPGetPC(ksp, &kpc);
                if (std::strcmp(pcs[i], "none") == 0)
                {
                    PCSetType(kpc, PCNONE);
                }
                else if (std::strcmp(pcs[i], "icc") == 0)
                {
                    PCSetType(kpc, PCICC);
                    if (levels_ > 0) PCFactorSetLevels(kpc, levels_);
                }
                else if (std::strcmp(pcs[i], "ilu") == 0)
                {
                    PCSetType(kpc, PCILU);
                    if (levels_ > 0) PCFactorSetLevels(kpc, levels_);
                }
                else
                {
                    PCSetType(kpc, PCJACOBI);
                }
                KSPSetTolerances(ksp, 1e-8, PETSC_DEFAULT, PETSC_DEFAULT, 20000);
                VecSet(xv2, 0.0);
                KSPSolve(ksp, bv, xv2);
                PetscInt its = 0;
                KSPGetIterationNumber(ksp, &its);
                KSPConvergedReason reason;
                KSPGetConvergedReason(ksp, &reason);
                Info<< "PETSC-CGCOMPARE: pc=" << pcs[i]
                    << " levels=" << levels_
                    << " iterations=" << its
                    << " reason=" << int(reason)
                    << endl;
                KSPDestroy(&ksp);
            }
            VecDestroy(&bv); VecDestroy(&xv2);
        }
    }

    // ★ THE ACCOUNTING BUG (fixed 2026-10-11):
    //   This gate used to guard the WHOLE report(), including the CSV write.
    //   But one time index holds 3 pressure solves, each with its OWN
    //   preconditioner instance and its own buildPC(). Gating the write meant
    //   the CSV held only the FIRST solve of each step, so ΣtPCSetup summed to
    //   1/3 of the truth (2.458 s vs the real 7.371 s at K=1).
    //
    //   Now the gate covers ONLY the expensive tIter repetitions (8 apply
    //   calls); the CSV row is written for EVERY solve. Column 2 keeps the
    //   tIter measurement; rows with an empty rep flag are cheap.
    bool measureIter = false;
    {
        static std::set<std::pair<label, word>> done;
        measureIter = done.insert(std::make_pair(timeIndex_, fieldTag_)).second;
    }

    const scalarField& diag  = M.diag();
    const scalarField& upper = M.upper();
    const scalarField& lower = M.hasLower() ? M.lower() : M.upper();
    const labelList& uAddr = M.lduAddr().upperAddr();
    const labelList& lAddr = M.lduAddr().lowerAddr();

    const label nCells = diag.size();
    const label nFaces = upper.size();

    const label origReps = reps_;

    double ma = -1.0, mp = -1.0, tIter = -1.0;

    if (measureIter)
    {
        solveScalarField x(nCells, 1.0);
        solveScalarField w(nCells, 0.0);

        std::vector<double> tAmul, tApply;
        tAmul.reserve(reps_);
        tApply.reserve(reps_);

        // ★ Guard: the repetitions below are an isolated cold-cache
        //   measurement. They must NOT be added to the in-loop accumulators,
        //   otherwise the reported in-loop apply cost would be inflated.
        inReport_ = true;

        for (label rep = 0; rep < reps_; rep++)
        {
            const double a0 = wallSeconds();
            amulReplica(w, x, diag, upper, lower, uAddr, lAddr);
            const double a1 = wallSeconds();
            tAmul.push_back(a1 - a0);

            const double p0 = wallSeconds();
            this->precondition(w, x, 0);
            const double p1 = wallSeconds();
            tApply.push_back(p1 - p0);
        }

        inReport_ = false;

        ma = medianOf(tAmul);
        mp = medianOf(tApply);
        tIter = ma + mp;
    }

    // r uses the FACTORISATION time only (t_pcsetup), NOT t_convert.
    const double r = (tIter > 0.0) ? tPCSetup_/tIter : -1.0;

    // ★ A2: hand the freshly measured r to the online policy. Only rows that
    //   actually re-factored carry a meaningful tPCSetup; a reuse row would
    //   give r ~ 0 and would corrupt the criterion.
    if (online_ && r > 0.0 && reusedFrom_ < 0)
    {
        onlineCache()[fieldTag_].rSamples.push_back(r);
    }

    // Also report the total relay+factor cost, for engineering completeness
    const double rTotal = (tIter > 0.0) ? (tConvert_ + tPCSetup_)/tIter : -1.0;

    if (!outPath_.empty())
    {
        std::ofstream os(outPath_.c_str(), std::ios::app);
        if (os.good())
        {
            os << timeIndex_ << ',' << fieldTag_ << ','
               << kind_ << ',' << levels_ << ','
               << nCells << ',' << nFaces << ','
               // rep field: -1 for the plain per-solve rows, reps_ for the
               // one row per step that also carries the isolated tIter
               << (measureIter ? origReps : -1) << ','
               << freezeAt_ << ',' << (reusedFrom_ >= 0 ? 1 : 0) << ','
               << period_ << ',' << reusedFrom_ << ','
               << (adopted_ ? 1 : 0) << ','
               << tFreeze_ << ','
               << tConvert_ << ',' << tPCSetup_ << ',' << tAssemble_ << ','
               << ma << ',' << mp << ',' << tIter << ','
               << r << ',' << rTotal << ','
               // ★ In-loop apply accumulators (static, survive across the
               //   1032 per-solve preconditioner instances)
               << s_tApplyAccum_ << ',' << s_nApplyCalls_ << ','
               // ★ True buildPC totals (cross-check for the row sums)
               << s_tSetupAll_ << ',' << s_nBuildPC_ << '\n';
        }
    }

    if (lduMatrix::debug >= 1)
    {
        Info<< "PETSc " << kind_ << " lvl=" << levels_
            << (reusedFrom_ >= 0 ? " REUSE@" + Foam::name(reusedFrom_) : " rebuild")
            << " : t_freeze=" << tFreeze_*1e6 << "us"
            << " t_convert=" << tConvert_*1e6 << "us"
            << " t_assemble=" << tAssemble_*1e6 << "us"
            << " t_pcsetup=" << tPCSetup_*1e6 << "us"
            << " r=" << r
            << endl;
    }
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// ************************************************************************* //
