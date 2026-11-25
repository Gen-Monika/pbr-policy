set -e
source /root/autodl-tmp/envs/dealenv.sh
export PATH=/usr/bin:/bin:/root/miniconda3/bin:$PATH
R=/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex
B=/root/autodl-tmp/envs/aspect-2.4/build-pbr3
test ! -e "$B"
cmake -S "$R/aspect_source" -B "$B" -DCMAKE_BUILD_TYPE=Release -DDEAL_II_DIR=/root/autodl-tmp/envs/dealii-deb/usr/share/cmake/deal.II -DASPECT_UNITY_BUILD=ON -DASPECT_PRECOMPILE_HEADERS=ON
cmake --build "$B" -j2 --target aspect
