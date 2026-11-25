import re
P="/root/autodl-tmp/PBR"
TRE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
def times(p):
    return [float(m.group(1)) for m in (TRE.match(l) for l in open(p,errors="ignore")) if m]
for tag in ("fx","l20"):
    new=times("%s/w2%s_case/log.K1.r1"%(P,tag))
    old=times("%s/k2%s_case/log.K1.r1"%(P,tag))
    print("=== %s ===  old(endTime=1) %d 步   new(endTime=2) %d 步"%(tag,len(old),len(new)))
    print("  old[:4] =", ["%.6f"%x for x in old[:4]])
    print("  new[:4] =", ["%.6f"%x for x in new[:4]])
    n=min(len(old),len(new)); pref=0
    for i in range(n):
        if abs(new[i]-old[i])<1e-12: pref+=1
        else: break
    print("  公共前缀 = %d 步"%pref)
    print("  old 末步 = %.6f   new 中 t<=1.0 的步数 = %d"%(old[-1], sum(1 for t in new if t<=1.0)))
