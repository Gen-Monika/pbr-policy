#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 paper/draft_gemini/main.tex 重新展开 main_flat.tex（单文件底稿）。

规则（沿用 2026-10-24 的展开流程）：
  · 以 main.tex 为唯一结构来源，顶层 \\input{<文件>} 逐行替换成该文件的原文；
  · 表格仍以 \\input{tabs/tNN.tex} 保留（不展开，与历史版本一致）；
  · 各节前加 `% ===== BEGIN/END <文件名> =====` 标记，便于逐块替换；
  · 输出为 UTF-8（无 BOM）+ LF，与分章文件一致。
不要手改 main_flat.tex —— 章节改动后重跑本脚本。

用法：python3 code/paper/flatten_main.py [--check]
      --check 只比对，不写文件；不一致时以非零码退出。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "paper", "draft_gemini"))

INPUT_RE = re.compile(r"^\s*\\input\{([^}]+)\}\s*$")
# 这些 \\input 保留原样（不要展开）：
#   · tabs/ 表格一向不展开（历史版本如此）
#   · zihao.tex / preamble.tex 是导言区，保留 \\input 的形式（历史版本如此）
KEEP = ("tabs/", "zihao.tex", "preamble.tex")


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def flatten():
    main = read(os.path.join(ROOT, "main.tex"))
    out = []
    for line in main.split("\n"):
        m = INPUT_RE.match(line)
        if not m:
            out.append(line)
            continue
        name = m.group(1)
        if name.startswith(KEEP):
            out.append(line)
            continue
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            raise SystemExit("missing %s" % path)
        body = read(path).rstrip("\n")
        out.append("%% ===== BEGIN %s =====" % name)
        out.append(body)
        out.append("%% ===== END %s =====" % name)
    return "\n".join(out)


def main_():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    dst = os.path.join(ROOT, "main_flat.tex")
    new = flatten()
    old = read(dst) if os.path.exists(dst) else None
    if a.check:
        if old is not None and old == new:
            print("up to date")
            return 0
        print("STALE: main_flat.tex 与分章文件不一致")
        return 1
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print("written %s (%d bytes)" % (dst, os.path.getsize(dst)))
    return 0


if __name__ == "__main__":
    sys.exit(main_())
