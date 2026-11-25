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
    reused for all later time indices "a >= b".

    Rebuild (a <= b): rD_ computed from the matrix at time a   (normal DIC)
    Reuse   (a >  b): rD_ loaded from the freeze written at b  (this class)

    Control (environment variables):
      PBR_FREEZE_AT   : time index b at which to freeze (-1 = disabled)
      PBR_STORE       : directory for freeze files

    The field name (p_rgh, pcorr, ...) is taken automatically from
    sol.fieldName(), so different equations never share a freeze file.

\*---------------------------------------------------------------------------*/

#ifndef DICFrozenPreconditioner_H
#define DICFrozenPreconditioner_H

#include "lduMatrix.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

/*---------------------------------------------------------------------------*\
                  Class DICFrozenPreconditioner Declaration
\*---------------------------------------------------------------------------*/

class DICFrozenPreconditioner
:
    public lduMatrix::preconditioner
{
    // Private data

        //- The reciprocal preconditioned diagonal
        solveScalarField rD_;

        //- Freeze time index (-1 = disabled)
        label freezeAt_;

        //- Storage directory for freeze files
        fileName storeDir_;

        //- Field tag used in the freeze file name
        word fieldTag_;

        //- Whether this instance reused a frozen rD_
        bool reused_;


public:

    //- Runtime type information
    TypeName("DICFrozen");


    // Constructors

        //- Construct from matrix components and solver controls
        DICFrozenPreconditioner
        (
            const lduMatrix::solver&,
            const dictionary& solverControls
        );


    //- Destructor
    virtual ~DICFrozenPreconditioner() = default;


    // Member Functions

        //- Setup/apply/Amul micro-benchmark (env-gated, no side effects).
        //  Measures r = t_setup / (t_Amul + t_precondition) at time index a.
        void benchmark(const label a) const;

        //- Calculate the reciprocal of the preconditioned diagonal
        static void calcReciprocalD(solveScalarField&, const lduMatrix&);

        //- Return wA the preconditioned form of residual rA
        virtual void precondition
        (
            solveScalarField& wA,
            const solveScalarField& rA,
            const direction cmpt=0
        ) const;

        //- Report whether this instance reused a frozen diagonal
        bool reused() const noexcept { return reused_; }
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
