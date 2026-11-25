/**
 * 最小复现：逐步插桩，定位段错误发生在哪一个 PETSc 调用。
 * 参考对象：本项目已在 OpenFOAM 中稳定运行的 PETScPreconditioner，
 *           它用的是 MatCreate + MatSetSizes + MatSetType + MatSetUp
 *           + MatSetValues + MatAssembly。本文件复刻同一序列。
 */
#include <petsc.h>
#include <cstdio>
#include <vector>

#define STEP(msg) do { printf("  STEP: %s\n", msg); fflush(stdout); } while(0)
#define CK(x) do { PetscErrorCode _e = (x); \
    if (_e) { printf("    !! %s -> code %d\n", #x, (int)_e); fflush(stdout); \
              PetscFinalize(); return 1; } } while(0)

int main(int argc, char** argv)
{
    STEP("PetscInitialize");
    PetscInitialize(&argc, &argv, nullptr, nullptr);

    const PetscInt n = 20;
    STEP("build COO");
    std::vector<PetscInt> irow, icol;
    std::vector<PetscScalar> vval;
    for (PetscInt i = 0; i < n; i++)
    {
        irow.push_back(i); icol.push_back(i); vval.push_back(4.0);
        if (i + 1 < n)
        {
            irow.push_back(i);     icol.push_back(i + 1); vval.push_back(-1.0);
            irow.push_back(i + 1); icol.push_back(i);     vval.push_back(-1.0);
        }
    }
    const PetscInt nEnt = (PetscInt)irow.size();
    printf("    nnz = %d\n", (int)nEnt);

    STEP("MatCreate");
    Mat A;
    CK(MatCreate(PETSC_COMM_SELF, &A));

    STEP("MatSetSizes");
    CK(MatSetSizes(A, n, n, n, n));

    STEP("MatSetType SEQAIJ");
    CK(MatSetType(A, MATSEQAIJ));

    STEP("MatSetUp");
    CK(MatSetUp(A));

    STEP("MatSetValues");
    CK(MatSetValues(A, nEnt, irow.data(), nEnt, icol.data(),
                    vval.data(), INSERT_VALUES));

    STEP("MatAssemblyBegin");
    CK(MatAssemblyBegin(A, MAT_FINAL_ASSEMBLY));

    STEP("MatAssemblyEnd");
    CK(MatAssemblyEnd(A, MAT_FINAL_ASSEMBLY));

    STEP("MatView info");
    PetscInt m = 0, nn = 0;
    CK(MatGetSize(A, &m, &nn));
    printf("    size = %d x %d\n", (int)m, (int)nn);

    STEP("PCCreate");
    PC pc;
    CK(PCCreate(PETSC_COMM_SELF, &pc));

    STEP("PCSetType ILU");
    CK(PCSetType(pc, PCILU));

    STEP("PCFactorSetLevels 10");
    CK(PCFactorSetLevels(pc, 10));

    STEP("PCSetOperators");
    CK(PCSetOperators(pc, A, A));

    STEP("PCSetUp");
    CK(PCSetUp(pc));

    STEP("MatCreateVecs");
    Vec x, y;
    CK(MatCreateVecs(A, &x, &y));

    STEP("VecSet");
    CK(VecSet(x, 1.0));

    STEP("PCApply");
    CK(PCApply(pc, x, y));

    STEP("VecDestroy");
    CK(VecDestroy(&y));
    CK(VecDestroy(&x));

    STEP("PCDestroy");
    CK(PCDestroy(&pc));

    STEP("MatDestroy");
    CK(MatDestroy(&A));

    STEP("PetscFinalize");
    PetscFinalize();
    printf("ALL STEPS OK\n");
    return 0;
}
