/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Description
    PETSc-backed incomplete factorisation preconditioner for lduMatrix.

    Motivation
    ----------
    Measured 2026-10-10: every native OpenFOAM preconditioner has cost scale
    r = t_setup/(t_amul+t_apply) well below 1:

        DIC 0.36, DILU 0.32, FDIC 0.52, GAMG 0.07-0.96

    A reuse-vs-rebuild decision is only worth making when r is large enough
    that "rebuild now" is expensive relative to the iteration count, i.e. when
    the gain bound r/N is not negligible. Library-grade incomplete
    factorisations (with symbolic analysis and column ordering) reach

        PETSc ICC lvl=0..8  : r = 7.9  .. 82.6
        PETSc ILU lvl=0..8  : r = 11.5 .. 272
        SuperLU spilu       : r = 18.8 .. 354

    so this class exposes that regime to OpenFOAM by relaying lduMatrix to a
    PETSc Mat and using PCICC / PCILU.

    What is measured
    ----------------
    Three separate times, reported to a CSV:

      t_convert : lduMatrix -> PETSc Mat AIJ assembly
      t_pcsetup : PCSetUp (the incomplete factorisation itself)
      t_apply   : PCApply (one preconditioner application)

    r is defined from t_pcsetup only, so that it stays comparable with
    BandPC's t_b (their Table 2 caption: building time) and with the native
    OpenFOAM measurements. t_convert is reported separately because counting
    it as setup would inflate r relative to a native implementation that never
    needs the relay.

    Serial only (v1)
    ----------------
    Uses PETSC_COMM_SELF. In a parallel run each rank holds its own local
    matrix, so the preconditioner is block-Jacobi across ranks -- NOT the same
    as a global ILU. This is stated explicitly rather than silently assumed;
    parallel support is a separate decision (PCGBandit has 16-rank cases).

    Control (environment variables)
    -------------------------------
      PBR_PETSC_KIND   : "icc" or "ilu"          (default "icc")
      PBR_PETSC_LEVELS : fill levels, 0 = IC(0)  (default 0)
      PBR_PETSC_BENCH  : 1 = enable timing
      PBR_PETSC_OUT    : CSV to append records to
      PBR_PETSC_REPS   : apply reps (default 50)
      PBR_PETSC_FREEZE_AT : step b at which to snapshot the coefficients (-1 = off);
                            for a > b the preconditioner is built from that
                            snapshot while the solve still uses A_a, which is
                            exactly IT[a,b]
      PBR_PETSC_STORE  : snapshot directory
      PBR_PETSC_FREEZE_K    : periodic rebuild period K (-1 = off). Give it
                              WITHOUT PBR_PETSC_FREEZE_AT to generate snapshots on
                              every step; give both to run the period-K policy.
      PBR_PETSC_FREEZE_BASE : first base step of the periodic policy (default 100)

    ★ Online policy (A2)
    --------------------
      PBR_PETSC_ONLINE : 1 = run the ONLINE rebuild policy instead of any
                         fixed periodic schedule. The decision is remade at
                         each time step from statistics of PAST steps only
                         (strictly causal), so this is the policy that A1
                         validated offline, now executing in the real solver.
      PBR_PETSC_ONLINE_BASE : warm-up length b0 (default 100). For
                         timeIndex < b0 the preconditioner is rebuilt every
                         step; that is the frozen semantics of PBR and all
                         compared policies share it.
      PBR_PETSC_ONLINE_OUT  : CSV to append one decision record per step
                         (timeIndex, decision, age, est, avg, r, N).

\*---------------------------------------------------------------------------*/

#ifndef PETScPreconditioner_H
#define PETScPreconditioner_H

#include "lduMatrix.H"

#include <petsc.h>

namespace Foam
{

/*---------------------------------------------------------------------------*\
                  Class PETScPreconditioner Declaration
\*---------------------------------------------------------------------------*/

class PETScPreconditioner
:
    public lduMatrix::preconditioner
{
    // Private data

        //- PETSc matrix (CSR/AIJ) holding the relayed lduMatrix
        Mat A_;

        //- PETSc preconditioner context (PCICC or PCILU)
        PC pc_;

        //- Requested incomplete factorisation ("icc" | "ilu")
        word kind_;

        //- Fill levels (0 = IC(0)/ILU(0))
        label levels_;

        //- Scratch vectors for apply
        Vec x_, y_;

        //- Whether this instance was set up successfully
        bool valid_;

        //- Timing accumulators (seconds)
        scalar tConvert_;
        scalar tPCSetup_;

        //- ★ Cumulative time spent in the REAL CG-loop precondition() calls,
        //  and how many such calls happened. The isolated tIter measured in
        //  report() (one call on a cold cache) does NOT reflect the in-loop
        //  cost, which is what actually drives the wall clock.
        //
        //  STATIC: the preconditioner object is constructed once per solve()
        //  (1032 times per run), so per-instance accumulators would be reset
        //  constantly. These must survive across instances.
        static scalar s_tApplyAccum_;
        static label  s_nApplyCalls_;

        //- Set while report() is doing its isolated repetitions, so those
        //  calls are excluded from the in-loop accumulators above.
        mutable bool inReport_ = false;

        //- ★ How many times buildPC() actually ran, and how much tPCSetup it
        //  accumulated IN TOTAL. The CSV is written under a "once per time
        //  index" gate, so the per-row tPCSetup reflects only the FIRST solve
        //  of each step -- but a pressure step holds 3 solves, each with its
        //  own preconditioner instance. These statics capture the true total.
        static scalar s_tSetupAll_;
        static label  s_nBuildPC_;

        //- Whether timing is enabled
        bool timing_;

        //- Repetitions for the apply measurement
        label reps_;

        //- CSV path
        fileName outPath_;

        //- Time index of the current solve
        label timeIndex_;

        //- Field name
        word fieldTag_;

        //- Freeze time index b (-1 = disabled)
        label freezeAt_;

        //- Directory holding coefficient snapshots
        fileName storeDir_;

        //- Step b whose snapshot is being used (-1 = rebuild from current)
        label reusedFrom_;

        //- Time spent writing/reading the snapshot (seconds)
        scalar tFreeze_;

        //- Time spent relaying the lduMatrix into the PETSc Mat (seconds).
        //  This was previously outside every timer, which made the measured
        //  wall-clock saving exceed the model's prediction. Now timed.
        scalar tAssemble_;

        //- Periodic rebuild period K (-1 = single-point freeze mode)
        label period_;

        //- First step of the periodic policy
        label freezeBase_;

        //- Whether pc_/x_/y_ were adopted from the persistent per-field cache
        //  (if so this instance must NOT destroy them)
        bool adopted_;

        //- ★ A2: whether the online policy is driving freezeAt_/reusedFrom_
        bool online_;

        //- ★ A2: warm-up length b0 of the online policy
        label onlineBase_;


    // Private Member Functions

        //- Relay lduMatrix into the PETSc Mat (times itself into tConvert_)
        void buildPETScMatrix(const lduMatrix& M);

        //- Build the PETSc PC and factor it (times itself into tPCSetup_)
        void buildPC();

        //- Interleaved amul/apply measurement plus one CSV record
        void report(const lduMatrix& M) const;

        //- ★ A2: advance the online policy for the current time step and set
        //  freezeAt_/reusedFrom_ accordingly. Strictly causal: only statistics
        //  of steps strictly before timeIndex_ are used.
        void onlineDecide();

        //- ★ A2: feed one applied solve into the online accumulator
        void onlineNoteApply() const;

        //- ★ A2: append the current decision to the decision CSV
        void onlineLog() const;


public:

    //- Runtime type information
    TypeName("PETScBase");


    // Constructors

        PETScPreconditioner
        (
            const lduMatrix::solver&,
            const dictionary& solverControls,
            const char* defaultKind
        );


    //- Destructor
    virtual ~PETScPreconditioner();


    // Member Functions

        //- Return wA the preconditioned form of residual rA
        virtual void precondition
        (
            solveScalarField& wA,
            const solveScalarField& rA,
            const direction cmpt=0
        ) const;
};


/*---------------------------------------------------------------------------*\
              Class PETScICPreconditioner Declaration
\*---------------------------------------------------------------------------*/

//- Zero-fill incomplete Cholesky (PCICC). Registered as "PETScIC".
//  WARNING: measured 2026-10-10 on the damBreak pressure matrix, PCICC is
//  PATHOLOGICAL -- CG took 8732 iterations versus 75 with PCILU and 254 with
//  Jacobi. The pressure matrix has fixedFluxPressure/totalPressure boundaries
//  and is only semi-definite, so a Cholesky-type factor degenerates.
//  Prefer PETScILU for CFD pressure systems.
class PETScICPreconditioner
:
    public PETScPreconditioner
{
public:
    TypeName("PETScIC");
    PETScICPreconditioner(const lduMatrix::solver& s, const dictionary& d)
    : PETScPreconditioner(s, d, "icc") {}
    virtual ~PETScICPreconditioner() = default;
};


/*---------------------------------------------------------------------------*\
              Class PETScILUPreconditioner Declaration
\*---------------------------------------------------------------------------*/

//- Zero-fill incomplete LU (PCILU). Registered as "PETScILU".
//  Measured on the damBreak pressure matrix: 75 CG iterations (vs 48 for the
//  native DIC), i.e. a sane comparable-strength preconditioner.
class PETScILUPreconditioner
:
    public PETScPreconditioner
{
public:
    TypeName("PETScILU");
    PETScILUPreconditioner(const lduMatrix::solver& s, const dictionary& d)
    : PETScPreconditioner(s, d, "ilu") {}
    virtual ~PETScILUPreconditioner() = default;
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
