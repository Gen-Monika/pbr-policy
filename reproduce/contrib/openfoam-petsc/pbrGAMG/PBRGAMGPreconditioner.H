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

    See PBRGAMGPreconditioner.C for the rationale, the two-layer setup
    structure of GAMG, and the timing mechanics.

\*---------------------------------------------------------------------------*/

#ifndef PBRGAMGPreconditioner_H
#define PBRGAMGPreconditioner_H

#include "GAMGPreconditioner.H"

#include <chrono>
#include <utility>
#include <set>
#include <vector>

namespace Foam
{

/*---------------------------------------------------------------------------*\
                        Class TimerBase Declaration
\*---------------------------------------------------------------------------*/

//- Records a wall-clock start time BEFORE GAMGPreconditioner's constructor
//  runs, purely by virtue of being listed earlier in the base-class list.
class TimerBase
{
protected:

    double tStart_;

public:

    TimerBase()
    :
        tStart_(std::chrono::duration<double>
        (
            std::chrono::steady_clock::now().time_since_epoch()
        ).count())
    {}

    virtual ~TimerBase() = default;

    double elapsed() const
    {
        const double now = std::chrono::duration<double>
        (
            std::chrono::steady_clock::now().time_since_epoch()
        ).count();
        return now - tStart_;
    }
};


/*---------------------------------------------------------------------------*\
                  Class PBRGAMGPreconditioner Declaration
\*---------------------------------------------------------------------------*/

class PBRGAMGPreconditioner
:
    public TimerBase,               // must precede GAMGPreconditioner
    public GAMGPreconditioner
{
    // Private data

        //- Collected apply times (seconds)
        mutable std::vector<double> applyTimes_;

        //- Time index of the solve this instance belongs to
        label timeIndex_;

        //- Whether timing is enabled
        bool timing_;

        //- Repetitions for the apply/amul measurement
        label reps_;

        //- Setup time (seconds), from TimerBase
        double setupTime_;

        //- Output CSV path
        string outPath_;


    // Private Member Functions

        //- Interleaved amul/apply measurement plus one CSV record
        void report(const lduMatrix& M) const;

        //- Median of a sample (sorts a copy)
        static double median(std::vector<double> v);


public:

    //- Runtime type information
    TypeName("PBRGAMG");


    // Constructors

        PBRGAMGPreconditioner
        (
            const lduMatrix::solver&,
            const dictionary& solverControls
        );


    //- Destructor
    virtual ~PBRGAMGPreconditioner();


    // Member Functions

        //- Return wA the preconditioned form of residual rA (nVcycles_ V-cycles)
        virtual void precondition
        (
            solveScalarField& wA,
            const solveScalarField& rA,
            const direction cmpt=0
        ) const;
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
