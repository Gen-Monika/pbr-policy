#!/usr/bin/env python3
"""把 b0 固定回 100（与原版 greedy_v6 一致），避免各策略间预热期记账不一致。"""
p = "online_cross.py"
s = open(p).read()
before = s
s = s.replace("    b0 = min(100, max(1, T // 4))", "    b0 = 100")
s = s.replace('    print("  （预热期 b0=%d 步）" % b0)', '    print("  （预热期 b0=100 步）")')
if s == before:
    print("WARN: 未发生替换（请检查当前内容）")
else:
    open(p, "w").write(s)
    print("OK: b0 已固定为 100")
