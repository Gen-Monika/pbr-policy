/*---------------------------------------------------------------------------*\
Class
    Foam::PBRPCGReport

Description
    在程序退出时输出 PBRPCG 的累计统计。
    用静态对象的析构函数作为 atexit 钩子（顺序在 PETSc 之前不重要，
    因为只是写文件）。
\*---------------------------------------------------------------------------*/

#include "PBRPCG.H"

#include <cstdlib>

namespace Foam
{

namespace
{
    struct PBRPCGReporter
    {
        ~PBRPCGReporter()
        {
            // 仅在启用时输出
            if (std::getenv("PBR_SOLVER_OUT"))
            {
                PBRPCG::report();
            }
        }
    };

    // 静态实例：其析构在 main 结束后自动触发
    PBRPCGReporter pbrPCGReporter_;
}

} // End namespace Foam

// ************************************************************************* //
