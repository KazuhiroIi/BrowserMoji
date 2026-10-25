"""静止画を ASCII アートに変換する（方式 A / B の比較出力）。

使い方:
    uv run python convert.py --input path/to/img.png [--input ...] [--cols 80]
        [--charset all] [--edge-thr 0.14] [--out out]
    --input の代わりに --synth を付けると out/synth/ の合成画像すべてを処理する。

実機写真は data/ 配下に置く想定。--input でパスを渡せば差し替わる
（合成画像への依存はこの CLI の引数だけ）。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import charset
import config
import glyphfeat
import render
import selector

HERE = Path(__file__).resolve().parent
DEFAULT_FEATURES = HERE / "out" / "assets" / "features.json"
DEFAULT_ATLAS = HERE / "out" / "assets" / "atlas.png"
DEFAULT_FONT = HERE / "fonts" / "NotoSansJP-Regular.otf"


def load_gray(path: Path) -> np.ndarray:
    """画像を読み、0..1 のグレースケール（1=白）で返す。"""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    return gray


def preprocess(gray: np.ndarray, cols: int, fs: int):
    """列数 cols（セルは正方形）になるよう縮小し、作業用画像とグリッドを返す。"""
    h, w = gray.shape
    rows = max(1, round(cols * h / w))
    work = cv2.resize(gray, (cols * fs, rows * fs), interpolation=cv2.INTER_AREA)
    return work, rows, cols


def convert_one(path: Path, ids_table: list[dict], atlas: np.ndarray, atlas_meta: dict,
                cols: int, edge_thr: float, out_dir: Path, font_path: Path) -> dict:
    fs = atlas_meta["featurePx"]
    cell_px = atlas_meta["cellPx"]
    atlas_cols = atlas_meta["atlasCols"]
    norms = glyphfeat.dol_normalizations(fs)

    t0 = time.perf_counter()
    gray = load_gray(path)
    work, rows, n_cols = preprocess(gray, cols, fs)
    t_pre = time.perf_counter() - t0

    ink = glyphfeat.ink_from_gray(work)
    sel_a = selector.SelectorA(ids_table, edge_threshold=edge_thr)
    sel_b = selector.SelectorB(ids_table)

    # --- 方式 A ---
    t0 = time.perf_counter()
    lum = glyphfeat.block_mean(work, rows, n_cols, fs)
    gx, gy = glyphfeat.sobel_grads(work)
    gmag_all = np.hypot(gx, gy)
    # エッジの検出にはセル内最大 |勾配| を使う（セル平均は細いエッジを 1/fs に希釈する）
    gmag = glyphfeat.block_max(gmag_all, rows, n_cols, fs)
    gmag_mean = glyphfeat.block_mean(gmag_all, rows, n_cols, fs)
    gvec = np.stack([glyphfeat.block_mean(gx, rows, n_cols, fs),
                     glyphfeat.block_mean(gy, rows, n_cols, fs)], axis=-1)
    ids_a = sel_a.select(lum, gmag, gvec, gmag_mean)
    t_a = time.perf_counter() - t0

    # --- 方式 B ---
    t0 = time.perf_counter()
    density, dir8, region4 = glyphfeat.cell_features_b(ink, rows, n_cols, fs, norms)
    ids_b = sel_b.select(density, dir8, region4)
    t_b = time.perf_counter() - t0

    # --- 描画 ---
    t0 = time.perf_counter()
    img_a = render.render_ascii(ids_a, atlas, atlas_cols, cell_px)
    img_b = render.render_ascii(ids_b, atlas, atlas_cols, cell_px)
    t_render = time.perf_counter() - t0

    # 入力パネルはセルグリッドに合わせて拡大縮小して並べる
    input_panel = Image.fromarray((work * 255).round().astype(np.uint8), mode="L")
    panels = [
        ("入力 (input)", input_panel),
        (f"方式 A (輝度+エッジ)  {t_a*1000:.0f} ms", img_a),
        (f"方式 B (最近傍)      {t_b*1000:.0f} ms", img_b),
    ]
    cmp_img = render.comparison(panels, font_path)

    out_cmp = out_dir / "compare"
    out_ascii = out_dir / "ascii"
    out_cmp.mkdir(parents=True, exist_ok=True)
    out_ascii.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    cmp_path = out_cmp / f"{stem}_c{cols}.png"
    cmp_img.save(cmp_path)
    img_a.save(out_ascii / f"{stem}_a.png")
    img_b.save(out_ascii / f"{stem}_b.png")

    return {
        "input": str(path), "cols": n_cols, "rows": rows, "cells": rows * n_cols,
        "t_preprocess_ms": t_pre * 1000, "t_a_ms": t_a * 1000, "t_b_ms": t_b * 1000,
        "t_render_ms": t_render * 1000,
        "compare": str(cmp_path),
        "ascii_a": str(out_ascii / f"{stem}_a.png"),
        "ascii_b": str(out_ascii / f"{stem}_b.png"),
    }


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="静止画 → ASCII（方式 A / B 比較）")
    ap.add_argument("--input", type=Path, action="append", help="入力画像（複数回指定可）")
    ap.add_argument("--synth", action="store_true", help="out/synth/ の合成画像をすべて処理")
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--charset", default="all", choices=list(charset.CHARSET_PRESETS))
    ap.add_argument("--edge-thr", type=float, default=config.EDGE_THRESHOLD)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    args = ap.parse_args()

    import json
    data = json.loads(args.features.read_text(encoding="utf-8"))
    meta = data["meta"]
    if meta["charsetPreset"] != args.charset:
        raise SystemExit(
            f"features.json は charset={meta['charsetPreset']} で生成されています。"
            f"--charset {meta['charsetPreset']} を指定するか、atlas.py を再実行してください。"
        )
    records = data["chars"]
    atlas_img = Image.open(args.atlas)
    atlas = np.asarray(atlas_img.convert("L"))

    if args.synth:
        inputs = sorted((HERE / "out" / "synth").glob("*.png"))
        if not inputs:
            raise SystemExit("out/synth/ に画像がありません。先に `uv run python synth.py` を実行してください。")
    elif args.input:
        inputs = args.input
    else:
        raise SystemExit("--input か --synth を指定してください。")

    for p in inputs:
        r = convert_one(Path(p), records, atlas, meta, args.cols, args.edge_thr, args.out, DEFAULT_FONT)
        print(f"{Path(r['input']).name}: {r['cols']}x{r['rows']} cells  "
              f"A={r['t_a_ms']:.0f}ms  B={r['t_b_ms']:.0f}ms  render={r['t_render_ms']:.0f}ms")
        print(f"  compare -> {r['compare']}")


if __name__ == "__main__":
    main()
