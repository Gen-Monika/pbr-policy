/* Infrastructure check only: two real ranks, a collective, and MPI identity.
 * No solver/physics or policy code. Built with the selected host's MPI wrapper.
 * Verify PBR_MPI_OK and compare its resolved libmpi with the host in the report.
 * Rollback: stop selecting this check; retain its job directory for diagnostics. */
#include <mpi.h>
#include <stdio.h>
int main(int argc, char **argv) {
    int rank, size, total = -1, len = 0;
    char version[MPI_MAX_LIBRARY_VERSION_STRING];
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Allreduce(&rank, &total, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
    MPI_Get_library_version(version, &len);
    printf("PBR_MPI_RANK rank=%d size=%d\n", rank, size);
    if (rank == 0) {
        printf("PBR_MPI_LIBRARY %.*s\n", len, version);
        if (size == 2 && total == 1) printf("PBR_MPI_OK size=2 sum=1\n");
    }
    MPI_Finalize();
    return size == 2 && total == 1 ? 0 : 1;
}
