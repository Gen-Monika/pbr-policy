/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | www.openfoam.com
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Class
    Foam::PBRPCG
\*---------------------------------------------------------------------------*/

#include "PBRPCG.H"
#include "lduMatrix.H"
#include "addToRunTimeSelectionTable.H"
#include "Time.H"
#include "objectRegistry.H"
#include "OSspecific.H"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

namespace
{
    //- 单调时钟（与 PETScPreconditioner.C 中的 wallSeconds 同义）
    inline double pbrWallSeconds()
    {
        using namespace std::chrono;
        return duration<double>(steady_clock::now().time_since_epoch()).count();
    }
}

// Static data
scalar PBRPCG::s_totalSolveTime_     = 0.0;
scalar PBRPCG::s_totalConstructTime_ = 0.0;
label  PBRPCG::s_nConstruct_         = 0;
label  PBRPCG::s_nSolve_             = 0;
label  PBRPCG::s_timeIndex_          = -1;
bool   PBRPCG::s_initialised_        = false;
FILE*  PBRPCG::s_fp_                 = nullptr;

defineTypeNameAndDebug(PBRPCG, 0);

// 与 PCG.C 相同的注册方式：
// addToRunTimeSelectionTable 宏在此处展开的名字与 symMatrix 表不匹配，
// 故直接实例化嵌套构造表成员（PCG.C 即如此）。
lduMatrix::solver::addsymMatrixConstructorToTable<PBRPCG>
    addPBRPCGSymMatrixConstructorToTable_;

// 注意：PCG 只支持对称矩阵，故不注册 asymMatrix



void Foam::PBRPCG::initAccumulator()
{
    if (s_initialised_) return;
    s_initialised_ = true;

    const char* p = std::getenv("PBR_SOLVER_OUT");
    if (p && *p)
    {
        s_fp_ = std::fopen(p, "w");
        if (s_fp_)
        {
            std::fprintf(s_fp_,
                "timeIndex,which,solveTime,nConstruct,nSolve,tConstructAccum\n");
            std::fflush(s_fp_);
        }
    }

    Info<< "PBRPCG: solver-level timing enabled"
        << (s_fp_ ? " (writing " + std::string(std::getenv("PBR_SOLVER_OUT")) + ")"
                  : " (no PBR_SOLVER_OUT, summary only)")
        << endl;
}


Foam::PBRPCG::PBRPCG
(
    const word& fieldName,
    const lduMatrix& matrix,
    const FieldField<Field, scalar>& interfaceBouCoeffs,
    const FieldField<Field, scalar>& interfaceIntCoeffs,
    const lduInterfaceFieldPtrsList& interfaces,
    const dictionary& solverControls
)
:
    PCG
    (
        fieldName,
        matrix,
        interfaceBouCoeffs,
        interfaceIntCoeffs,
        interfaces,
        solverControls
    )
{
    initAccumulator();

    const double t0 = pbrWallSeconds();

    s_timeIndex_ = label(matrix.mesh().thisDb().time().timeIndex());
    s_nConstruct_++;

    s_totalConstructTime_ += (pbrWallSeconds() - t0);
}


Foam::PBRPCG::~PBRPCG()
{
    const double t0 = pbrWallSeconds();
    s_totalConstructTime_ += (pbrWallSeconds() - t0);
}


Foam::solverPerformance Foam::PBRPCG::scalarSolve
(
    solveScalarField& psi,
    const solveScalarField& source,
    const direction cmpt
) const
{
    const double t0 = pbrWallSeconds();

    solverPerformance sp = PCG::scalarSolve(psi, source, cmpt);

    const double dt = pbrWallSeconds() - t0;
    s_totalSolveTime_ += dt;
    s_nSolve_++;

    if (s_fp_)
    {
        std::fprintf(s_fp_, "%d,solve,%g,%d,%d,%g\n",
                     (int)s_timeIndex_, (double)dt,
                     (int)s_nConstruct_, (int)s_nSolve_,
                     (double)s_totalConstructTime_);
        if (s_nSolve_ % 32 == 0) std::fflush(s_fp_);
    }

    return sp;
}


void Foam::PBRPCG::report()
{
    Info<< "PBRPCG SUMMARY:"
        << " nConstruct=" << s_nConstruct_
        << " nSolve=" << s_nSolve_
        << " totalSolveTime=" << s_totalSolveTime_ << "s"
        << " totalConstructTime=" << s_totalConstructTime_ << "s"
        << endl;

    const char* p = std::getenv("PBR_SOLVER_OUT");
    if (p && *p)
    {
        FILE* f = std::fopen(p, "a");
        if (f)
        {
            std::fprintf(f, "SUMMARY,summary,%g,%d,%d,%g\n",
                         (double)s_totalSolveTime_,
                         (int)s_nConstruct_, (int)s_nSolve_,
                         (double)s_totalConstructTime_);
            std::fclose(f);
        }
    }

    if (s_fp_)
    {
        std::fclose(s_fp_);
        s_fp_ = nullptr;
    }
}

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// ************************************************************************* //
