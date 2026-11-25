#!/usr/bin/env python3
"""Analyze wallclock_small batch: ws<cfg>r<round>_pc_<mode>_r1.csv + logs."""
import glob, os, re, statistics, sys

def parse_pc(path):
    sc=ss=0.0; mas=[]; last=None; nbuild=0
    for line in open(path):
        p=line.rstrip("\n").split(",")
        if len(p)<25 or p[1].strip()!="p_rgh": continue
        sc+=float(p[13]); ss+=float(p[14])
        ma=float(p[16])
        if ma>=0: mas.append(ma)
        if p[8].strip()!="1": nbuild+=1
        last=p
    if last is None: return None
    mm=statistics.median(mas) if mas else 0.0
    ta,nc=float(last[21]),float(last[22])
    return dict(conv=sc, setup=ss, tapply=ta, ncalls=nc,
                total=sc+ss+ta+mm*nc, nbuild=nbuild,
                tsetup_all=float(last[23]))

def parse_logs(path):
    PAT=re.compile(r"^round=\d+ mode=(\w+) wall_ms=(\d+) execTime=([\d.]+) iters=(\d+) steps=(\d+) rbsteps=(\S*) fatal=(\d+) load=([\d.]+)/([\d.]+)")
    d={}
    for f in glob.glob(path + "/*.log"):
        cfg=re.search(r"_([a-z0-9]+)\.log$", f).group(1)
        if cfg=="status": continue
        rnd=0
        for line in open(f):
            m=re.match(r"### \w+ round (\d)", line)
            if m: rnd=int(m.group(1)); continue
            m=PAT.match(line)
            if m: d[(cfg,rnd,m.group(1))]=dict(
                wall=int(m.group(2))/1000, exec=float(m.group(3)),
                iters=int(m.group(4)), steps=int(m.group(5)), rb=m.group(6),
                fatal=int(m.group(7)), load=(float(m.group(8)),float(m.group(9))))
    return d

def main(csvdir, logdir):
    pc={}
    for f in glob.glob(csvdir + "/*_pc_*.csv"):
        m=re.match(r"ws(.+?)r(\d)_pc_(\w+)_r(\d+)\.csv$", os.path.basename(f))
        if not m: print("UNMATCHED", f); continue
        cfg,rnd,mode=m.group(1),int(m.group(2)),m.group(3)
        v=parse_pc(f)
        if v: pc[(cfg,rnd,mode)]=v
    lg=parse_logs(logdir)
    cfgs=sorted({k[0] for k in pc})
    print(f"configs={cfgs}  pc_rows={len(pc)}  log_rows={len(lg)}")

    print("\n=== fatal check ===")
    print(f"total runs={len(lg)}  fatal!=0: {[k for k,v in lg.items() if v['fatal']]}")

    print("\n=== pressure-module saving per round (K1 vs ONLp / K1 vs K3) ===")
    print("cfg  rnd  K1tot   ONLptot  K3tot   ONLp_save% K3_save%  nbuild(K1/ONL)")
    for cfg in cfgs:
        rounds=sorted({k[1] for k in pc if k[0]==cfg})
        for r in rounds:
            k1=pc.get((cfg,r,"K1")); on=pc.get((cfg,r,"ONLp")); k3=pc.get((cfg,r,"K3"))
            if not (k1 and on): continue
            s_on=(1-on["total"]/k1["total"])*100
            s_k3=(1-k3["total"]/k1["total"])*100 if k3 else float("nan")
            print(f"{cfg:4s} {r}  {k1['total']:7.3f} {on['total']:8.3f} "
                  f"{(k3['total'] if k3 else float('nan')):7.3f}  {s_on:9.2f} {s_k3:8.2f}  "
                  f"{k1['nbuild']}/{on['nbuild']}")
        vals=[(1-pc[(cfg,r,"ONLp")]["total"]/pc[(cfg,r,"K1")]["total"])*100
              for r in rounds if (cfg,r,"K1") in pc and (cfg,r,"ONLp") in pc]
        if vals:
            k1s=[pc[(cfg,r,"K1")]["total"] for r in rounds if (cfg,r,"K1") in pc]
            ons=[pc[(cfg,r,"ONLp")]["total"] for r in rounds if (cfg,r,"ONLp") in pc]
            rom=(1-statistics.median(ons)/statistics.median(k1s))*100
            print(f"  -> {cfg}: n={len(vals)} median={statistics.median(vals):.2f} "
                  f"range={min(vals):.2f}-{max(vals):.2f} spread={max(vals)-min(vals):.1f}pp "
                  f"ratioMed={rom:.2f} stdev={statistics.stdev(vals) if len(vals)>1 else 0:.2f}\n")

    print("=== e2e ExecutionTime + paired ONLp/K3, ONLp/DIC ===")
    for cfg in cfgs:
        rounds=sorted({k[1] for k in lg if k[0]==cfg})
        for mode in ("K1","K3","ONLp","DIC"):
            vs=[lg[(cfg,r,mode)]["exec"] for r in rounds if (cfg,r,mode) in lg]
            if vs: print(f"{cfg:4s} {mode:5s} n={len(vs)} med={statistics.median(vs):8.2f} "
                         f"vals=[{' '.join(f'{v:.2f}' for v in vs)}]")
        for base in ("K3","DIC"):
            rs=[lg[(cfg,r,"ONLp")]["exec"]/lg[(cfg,r,base)]["exec"] for r in rounds
                if (cfg,r,"ONLp") in lg and (cfg,r,base) in lg]
            if rs: print(f"  ONLp/{base}: median={statistics.median(rs):.4f} "
                         f"range={min(rs):.3f}-{max(rs):.3f}")
        print()

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
