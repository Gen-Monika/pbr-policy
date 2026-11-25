import json
D=json.load(open("/tmp/final3.json"))
TAGS=["fx","l15","l20","fine","x3","fl30","sth"]
for mode,lab in [("r1","rho = r1"),("sr1","rho = s*r1")]:
    print("="*128); print("★ 口径 %s"%lab); print("="*128)
    print("  %-6s %9s | %-8s %-8s %-8s %-8s | %-8s %-8s | %-8s %-8s | %-8s %-6s %-8s"%
      ("配置","oracle","K=1","K*","在线","完美信念","Chalm2.0","Chalm f*","REAC120","20%","在线vsK*","f*","在线vsChalm"))
    for t in TAGS:
        r=D[mode][t]; o=r["orc"]; g=lambda k:100*(r[k]/o-1)
        print("  %-6s %9.0f | %+7.2f%% %+7.2f%% %+7.2f%% %+7.2f%% | %+7.2f%% %+7.2f%% | %+7.2f%% %+7.2f%% | %+7.2f%% %6.2f %+7.2f%%"%(
          t,o,g("K1"),g("fix"),g("onl"),g("pf"),g("ch"),g("cs"),g("re"),g("ra"),
          100*(r["onl"]/r["fix"]-1),r["fs"],100*(r["onl"]/r["ch"]-1)))
    n=len(TAGS)
    def w(k,ref): return sum(1 for t in TAGS if D[mode][t][k]<D[mode][t][ref])
    print("\n  ★ 在线    : 赢 Chalm2.0 %d/%d | 赢 REAC120 %d/%d | 赢 20%% %d/%d"%(w("onl","ch"),n,w("onl","re"),n,w("onl","ra"),n))
    print("  ★ 完美信念: 赢 K* %d/%d | 赢 Chalm2.0 %d/%d | 赢 Chalm f* %d/%d | 赢 REAC120 %d/%d"%(w("pf","fix"),n,w("pf","ch"),n,w("pf","cs"),n,w("pf","re"),n))
    print("  ★ 先知型(Chalm) 相对 oracle: "+", ".join("%s %+.1f%%"%(t,100*(D[mode][t]["ch_cl"]/D[mode][t]["orc"]-1)) for t in TAGS))
    print("  ★ f* 分布: "+", ".join("%s=%.2f"%(t,D[mode][t]["fs"]) for t in TAGS))
    print("  ★ REAC 最优阈值: "+", ".join("%s=%d"%(t,D[mode][t]["restar"]) for t in TAGS))
    print()
