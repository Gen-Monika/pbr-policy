#!/usr/bin/env python3
"""把 damBreak 的 blockMeshDict 分辨率加密 N 倍（几何顶点/scale 不动）。"""
import sys
p = sys.argv[1]
dv = int(sys.argv[2]) if len(sys.argv) > 2 else 2
s = open(p).read()
old = """    hex (0 1 5 4 12 13 17 16) (23 8 1) simpleGrading (1 1 1)
    hex (2 3 7 6 14 15 19 18) (19 8 1) simpleGrading (1 1 1)
    hex (4 5 9 8 16 17 21 20) (23 42 1) simpleGrading (1 1 1)
    hex (5 6 10 9 17 18 22 21) (4 42 1) simpleGrading (1 1 1)
    hex (6 7 11 10 18 19 23 22) (19 42 1) simpleGrading (1 1 1)"""
base = [(23,8),(19,8),(23,42),(4,42),(19,42)]
geo = ["(0 1 5 4 12 13 17 16)","(2 3 7 6 14 15 19 18)","(4 5 9 8 16 17 21 20)",
       "(5 6 10 9 17 18 22 21)","(6 7 11 10 18 19 23 22)"]
new = "\n".join("    hex %s (%d %d 1) simpleGrading (1 1 1)"
                % (geo[i], base[i][0]*dv, base[i][1]*dv) for i in range(5))
assert old in s, "blockMeshDict blocks not found"
open(p, "w").write(s.replace(old, new))
print("refined %dx per direction (%d cells expected)" % (dv, 2268*dv*dv))
