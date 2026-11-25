/**
 * 隔离微基准 v3：用 MatCreateSeqAIJWithArrays 直接传 CSR，
 * 避开 MatSetValues 的重复条目处理路径（v2 在 n>=200 时段错误）。
 *
 * 目的：在真实 damBreak 压力矩阵尺寸（2268×2268）上重复
 *       create → ILU(levels) → destroy 循环，检验每次重建的耗时
 *       是否随循环序号增长（累积效应假设）。
 */
#include <petsc.h>
#include <cstdio>
#include <chrono>
#include <vector>
#include <algorithm>
#include <numeric>

static inline double nowSeconds()
{
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

#define CK(x) do { PetscErrorCode _e = (x); \
    if (_e) { printf("FAIL line %d: %s -> %d\n", __LINE__, #x, (int)_e); \
              fflush(stdout); PetscFinalize(); return 1; } } while(0)

int main(int argc, char** argv)
{
    PetscInitialize(&argc, &argv, nullptr, nullptr);

    PetscInt n      = 2268;
    PetscInt levels = 10;
    PetscInt reps   = 344;
    PetscOptionsGetInt(nullptr, nullptr, "-n",      &n,      nullptr);
    PetscOptionsGetInt(nullptr, nullptr, "-levels", &levels, nullptr);
    PetscOptionsGetInt(nullptr, nullptr, "-reps",   &reps,   nullptr);

    printf("=== v3 (CSR): n=%d levels=%d reps=%d ===\n",
           (int)n, (int)levels, (int)reps);
    fflush(stdout);

    // ---- 构造 CSR：三对角 + 一条长程弱耦合（步长 17）----
    unsigned seed = 12345u;
    auto rnd = [&seed]() {
        seed = seed * 1103515245u + 12345u;
        return (double)((seed >> 16) & 0x7fff) / 32767.0;
    };

    std::vector<PetscInt>    ia(n + 1, 0);
    std::vector<PetscInt>    ja;
    std::vector<PetscScalar> a;
    ja.reserve((size_t)n * 7);
    a.reserve((size_t)n * 7);

    // 先统计每行非零数
    for (PetscInt i = 0; i < n; i++)
    {
        PetscInt cnt = 1;                       // 对角
        if (i > 0)         cnt++;               // 左邻
        if (i + 1 < n)     cnt++;               // 右邻
        if (i > 17)        cnt++;               // 长程左
        if (i + 17 < n)    cnt++;               // 长程右
        ia[i + 1] = ia[i] + cnt;
    }

    // 再填值（每行内列索引【升序】，PETSc 要求）
    std::vector<PetscScalar> diagv(n, 0.0);
    for (PetscInt i = 0; i < n; i++)
    {
        std::vector<PetscInt> cols;
        cols.push_back(i);
        if (i > 0)      { cols.push_back(i - 1); }
        if (i + 1 < n)  { cols.push_back(i + 1); }
        if (i > 17)     { cols.push_back(i - 17); }
        if (i + 17 < n) { cols.push_back(i + 17); }
        std::sort(cols.begin(), cols.end());
        cols.erase(std::unique(cols.begin(), cols.end()), cols.end());

        double diag = 1.0;
        for (size_t k = 0; k < cols.size(); k++)
        {
            const PetscInt j = cols[k];
            if (j == i) continue;
            const PetscScalar av = -(0.3 + 0.4 * rnd());
            ja.push_back(j);
            a.push_back(av);
            diag -= av;
        }
        ja.push_back(i);
        a.push_back(diag);
        // 保证该行内列索引升序：把对角插到正确位置
        const PetscInt s = ia[i], e = ia[i + 1];
        // 简单做法：重排这一段
        std::vector<std::pair<PetscInt, PetscScalar>> seg;
        for (PetscInt k = s; k < e; k++) seg.push_back({ja[k], a[k]});
        std::sort(seg.begin(), seg.end());
        for (PetscInt k = s; k < e; k++) { ja[k] = seg[k - s].first; a[k] = seg[k - s].second; }
    }

    printf("  CSR: nnz = %d\n", (int)ja.size());
    fflush(stdout);

    std::vector<double> times;
    times.reserve(reps);

    for (PetscInt r = 0; r < reps; r++)
    {
        if (r % 50 == 0) { printf("  rep %d ...\n", (int)r); fflush(stdout); }
        const double t0 = nowSeconds();

        Mat A;
        CK(MatCreateSeqAIJWithArrays(PETSC_COMM_SELF, n, n,
                                     ia.data(), ja.data(), a.data(), &A));
        CK(MatAssemblyBegin(A, MAT_FINAL_ASSEMBLY));
        CK(MatAssemblyEnd(A, MAT_FINAL_ASSEMBLY));

        PC pc;
        CK(PCCreate(PETSC_COMM_SELF, &pc));
        CK(PCSetType(pc, PCILU));
        CK(PCFactorSetLevels(pc, levels));
        CK(PCSetOperators(pc, A, A));
        CK(PCSetUp(pc));

        Vec x, y;
        CK(MatCreateVecs(A, &x, &y));
        CK(VecSet(x, 1.0));
        CK(PCApply(pc, x, y));

        CK(VecDestroy(&y));
        CK(VecDestroy(&x));
        CK(PCDestroy(&pc));
        CK(MatDestroy(&A));

        times.push_back(nowSeconds() - t0);
    }

    printf("\n  完成 %d 次循环\n", (int)reps);
    const int nseg = 8;
    const int seglen = reps / nseg;
    printf("\n  %-16s %-14s %-14s\n", "循环区间", "中位/ms", "均值/ms");
    for (int s = 0; s < nseg; s++)
    {
        const int lo = s * seglen;
        const int hi = (s == nseg - 1) ? (int)reps : (s + 1) * seglen;
        std::vector<double> seg(times.begin() + lo, times.begin() + hi);
        std::sort(seg.begin(), seg.end());
        double sum = std::accumulate(seg.begin(), seg.end(), 0.0);
        char label[32];
        std::snprintf(label, sizeof(label), "%3d - %3d", lo + 1, hi);
        printf("  %-16s %-14.3f %-14.3f\n", label,
               seg[seg.size() / 2] * 1e3, sum / seg.size() * 1e3);
    }

    std::vector<double> first(times.begin(), times.begin() + seglen);
    std::vector<double> last(times.end() - seglen, times.end());
    std::sort(first.begin(), first.end());
    std::sort(last.begin(), last.end());
    const double mf = first[first.size() / 2] * 1e3;
    const double ml = last[last.size() / 2] * 1e3;
    printf("\n  首段中位 = %.3f ms，末段中位 = %.3f ms，增长 = %+.2f%%\n",
           mf, ml, (ml / mf - 1.0) * 100.0);
    std::sort(times.begin(), times.end());
    printf("  全程中位 = %.3f ms\n", times[times.size() / 2] * 1e3);
    printf("\n  => 末段显著高于首段 ⇒ 累积效应成立\n");
    printf("  => 两端接近 ⇒ 累积效应不成立\n");

    PetscFinalize();
    return 0;
}
