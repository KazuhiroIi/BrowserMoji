"""1 フレーム処理時間の計測（EXP-2 の数値用）。

列数ごとに、前処理（グレースケール化＋縮小）/ 方式 A の選択 /
方式 B の選択（特徴量計算＋最近傍）/ 描画 の時間を分けて計測する。

使い方:
    uv run python bench.py [--input out/synth/edges.png] [--cols 48,80,120] [--trials 7]
結果は標準出力（Markdown 表）と out/bench.json に出力する。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

import config
import glyphfeat
import selector
from convert import DEFAULT_ATLAS, DEFAULT_FEATURES, load_gray, preprocess

HERE = Path(__file__).resolve().parent


def run_once(gray, cols, fs, sel_a, sel_b, norms, atlas, atlas_cols, cell_px, measure_render: bool):
    """1 フレームぶんの処理。段階ごとの時間 (s) を返す。"""
    t0 = time.perf_counter()
    work, rows, n_cols = preprocess(gray, cols, fs)
    t_pre = time.perf_counter() - t0

    ink = glyphfeat.ink_from_gray(work)

    t0 = time.perf_counter()
    lum = glyphfeat.block_mean(work, rows, n_cols, fs)
    gx, gy = glyphfeat.sobel_grads(work)
    gmag_all = np.hypot(gx, gy)
    gmag = glyphfeat.block_max(gmag_all, rows, n_cols, fs)
    gmag_mean = glyphfeat.block_mean(gmag_all, rows, n_cols, fs)
    gvec = np.stack([glyphfeat.block_mean(gx, rows, n_cols, fs),
                     glyphfeat.block_mean(gy, rows, n_cols, fs)], axis=-1)
    ids_a = sel_a.select(lum, gmag, gvec, gmag_mean)
    t_a = time.perf_counter() - t0

    t0 = time.perf_counter()
    density, dir8, region4 = glyphfeat.cell_features_b(ink, rows, n_cols, fs, norms)
    ids_b = sel_b.select(density, dir8, region4)
    t_b = time.perf_counter() - t0

    t_render = 0.0
    if measure_render:
        import render
        t0 = time.perf_counter()
        render.render_ascii(ids_a, atlas, atlas_cols, cell_px)
        t_render = time.perf_counter() - t0
    return rows, n_cols, t_pre, t_a, t_b, t_render


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="方式 A / B の 1 フレーム処理時間を計測する")
    ap.add_argument("--input", type=Path, default=HERE / "out" / "synth" / "edges.png")
    ap.add_argument("--cols", default=",".join(str(c) for c in config.BENCH_COLS))
    ap.add_argument("--trials", type=int, default=config.BENCH_TRIALS)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    ap.add_argument("--out", type=Path, default=HERE / "out" / "bench.json")
    args = ap.parse_args()

    data = json.loads(args.features.read_text(encoding="utf-8"))
    records = data["chars"]
    meta = data["meta"]
    fs, cell_px, atlas_cols = meta["featurePx"], meta["cellPx"], meta["atlasCols"]
    atlas = np.asarray(Image.open(args.atlas).convert("L"))
    sel_a = selector.SelectorA(records)
    sel_b = selector.SelectorB(records)
    norms = glyphfeat.dol_normalizations(fs)

    gray = load_gray(args.input)
    results = []
    for cols in [int(c) for c in args.cols.split(",")]:
        # ウォームアップ + 計測
        for i in range(args.trials):
            r = run_once(gray, cols, fs, sel_a, sel_b, norms, atlas, atlas_cols, cell_px,
                         measure_render=(i == args.trials - 1))
            if i == 0:
                rows = r[0]
                acc = {k: [] for k in ("pre", "a", "b", "render")}
            acc["pre"].append(r[2]); acc["a"].append(r[3]); acc["b"].append(r[4]); acc["render"].append(r[5])
        stat = {k: {"mean_ms": float(np.mean(v)) * 1000, "min_ms": float(np.min(v)) * 1000}
                for k, v in acc.items()}
        cells = rows * cols
        stat.update({"cols": cols, "rows": rows, "cells": cells,
                     "a_total_mean_ms": stat["pre"]["mean_ms"] + stat["a"]["mean_ms"] + stat["render"]["mean_ms"],
                     "b_total_mean_ms": stat["pre"]["mean_ms"] + stat["b"]["mean_ms"] + stat["render"]["mean_ms"]})
        results.append(stat)
        print(f"cols={cols:4d} ({cols}x{rows}, {cells} cells): "
              f"pre={stat['pre']['mean_ms']:.0f}ms  A={stat['a']['mean_ms']:.0f}ms  "
              f"B={stat['b']['mean_ms']:.0f}ms  render={stat['render']['mean_ms']:.0f}ms")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "input": str(args.input), "trials": args.trials, "results": results,
        "note": "Python (CPU) の基準実装。相対比較用であり、実機のfpsではない。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
