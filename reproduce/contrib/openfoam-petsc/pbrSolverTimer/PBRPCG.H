/*---------------------------------------------------------------------------*\
Class
    Foam::PBRPCG

Description
    PCG 的计时间包装：不改动 OpenFOAM 源码，注册为新的求解器名 PBRPCG，
    以便在 solve() 层面测量【压力求解的总耗时】。

    动机（PBR 项目）：
        wallclock - (本项目已计时的预条件子部分) 存在 8-11 s 未解释量，
        且该量随重建次数 K 变化。已确认非 p_rgh 场的迭代数与 K 无关，
        故未解释量必在压力求解路径内部。

    本类测量：
        tScalarSolve  : scalarSolve 的【总耗时】（含 CG 主循环 + 预条件子）
        nConstruct    : 构造次数
        nSolve        : scalarSolve 调用次数
        tConstruct    : 构造 + 析构的耗时

    与 PBR_PETSc 的 tPCSetup 之差即：
        CG 自身的 Amul / gSumProd / 向量更新 + 未覆盖的部分
\*---------------------------------------------------------------------------*/

#ifndef PBRPCG_H
#define PBRPCG_H

#include "PCG.H"
#include "IOstreams.H"
#include "OSspecific.H"
#include "Time.H"
#include "objectRegistry.H"

#include <cstdio>
#include <cstdlib>
#include <string>

namespace Foam
{

/*---------------------------------------------------------------------------*\
                            Class PBRPCG Declaration
\*---------------------------------------------------------------------------*/

class PBRPCG
:
    public PCG
{
    // Private Static Data

        //- 累计统计（跨实例，因为每次 solve 都会新建 PCG 对象）
        static scalar s_totalSolveTime_;
        static scalar s_totalConstructTime_;
        static label  s_nConstruct_;
        static label  s_nSolve_;
        static label  s_timeIndex_;
        static bool   s_initialised_;

        //- 已写出的快照（按时间步），用于逐步输出
        static FILE*  s_fp_;

    // Private Member Functions

        static void initAccumulator();

        PBRPCG(const PBRPCG&) = delete;
        void operator=(const PBRPCG&) = delete;

public:

    //- Runtime type information
    TypeName("PBRPCG");

    // Constructors

        PBRPCG
        (
            const word& fieldName,
            const lduMatrix& matrix,
            const FieldField<Field, scalar>& interfaceBouCoeffs,
            const FieldField<Field, scalar>& interfaceIntCoeffs,
            const lduInterfaceFieldPtrsList& interfaces,
            const dictionary& solverControls
        );

    //- Destructor
    virtual ~PBRPCG();

    // Member Functions

        //- Solve with timing
        virtual solverPerformance scalarSolve
        (
            solveScalarField& psi,
            const solveScalarField& source,
            const direction cmpt=0
        ) const;

        //- Flush accumulated statistics (call at exit)
        static void report();
};

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
