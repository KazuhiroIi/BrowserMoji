"""合成入力画像の生成（実機写真が用意されるまでの代用）。

滑らかなグラデーション / 幾何図形 / エッジが多い構造など、
文字選択方式の性格が現れやすい 4 枚を out/synth/ に出力する。

使い方:
    uv run python synth.py [--out out/synth] [--size 800x600]
実機写真は data/ 配下に置く想定。convert.py に --input で直接渡せる。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

import config

HERE = Path(__file__).resolve().parent


def _grad(w: int, h: int) -> np.ndarray:
    """斜め方向の滑らかなグラデーション + 柔らかい円形の明部。"""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    v = 0.55 + 0.30 * (x / w) - 0.25 * (y / h)
    cx, cy, r = w * 0.62, h * 0.40, h * 0.38
    v += 0.28 * np.exp(-(((x - cx) / r) ** 2 + ((y - cy) / r) ** 2))
    return np.clip(v, 0.0, 1.0)


def _shapes(w: int, h: int) -> np.ndarray:
    """はっきりしたエッジを持つ幾何図形。"""
    img = np.full((h, w), 0.92, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # 濃い円
    img[((xx - w * 0.30) ** 2 + (yy - h * 0.45) ** 2) < (h * 0.22) ** 2] = 0.10
    # 中間色の四角形（回転はしない）
    img[(xx > w * 0.52) & (xx < w * 0.78) & (yy > h * 0.22) & (yy < h * 0.58)] = 0.55
    # 三角形（辺の中点を結ぶ）
    tri = np.ones((h, w), dtype=bool)
    p = [(w * 0.62, h * 0.70), (w * 0.82, h * 0.70), (w * 0.72, h * 0.90)]
    for (x1, y1), (x2, y2) in ((p[0], p[1]), (p[1], p[2]), (p[2], p[0])):
        cross = (x2 - x1) * (yy - y1) - (y2 - y1) * (xx - x1)
        tri &= cross >= 0
    img[tri] = 0.30
    return img


def _edges(w: int, h: int) -> np.ndarray:
    """縞・市松・同心円などエッジが多い構図。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.full((h, w), 0.5, dtype=np.float32)
    # 斜め縞（左上）
    region = (xx < w * 0.5) & (yy < h * 0.5)
    img[region] = 0.5 + 0.45 * np.sign(np.sin((xx + yy)[region] * 2 * np.pi / 46.0))
    # 市松（右下）
    region = (xx >= w * 0.5) & (yy >= h * 0.5)
    img[region] = 0.25 + 0.5 * (((xx[region] // 40) + (yy[region] // 40)) % 2)
    # 同心円（右上）
    region = (xx >= w * 0.5) & (yy < h * 0.5)
    rr = np.sqrt((xx[region] - w * 0.75) ** 2 + (yy[region] - h * 0.25) ** 2)
    img[region] = 0.5 + 0.45 * np.sign(np.sin(rr * 2 * np.pi / 26.0))
    # 縦縞（左下）
    region = (xx < w * 0.5) & (yy >= h * 0.5)
    img[region] = 0.2 + 0.6 * ((xx[region] // 18) % 2)
    return img


def _vignette(w: int, h: int) -> np.ndarray:
    """逆光っぽい構図: 明るい窓 + 暗いシルエット（大きな楕円）。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = 0.85 - 0.25 * (yy / h)
    # 窓（長方形の明部）
    img[(xx > w * 0.55) & (xx < w * 0.95) & (yy > h * 0.08) & (yy < h * 0.52)] = 1.0
    # シルエット（暗い楕円2つ）
    e1 = ((xx - w * 0.30) / (w * 0.16)) ** 2 + ((yy - h * 0.55) / (h * 0.30)) ** 2
    img[e1 < 1.0] = 0.12
    e2 = ((xx - w * 0.30) / (w * 0.10)) ** 2 + ((yy - h * 0.28) / (h * 0.10)) ** 2
    img[e2 < 1.0] = 0.12
    return img


BUILDERS = {
    "gradient": _grad,      # 滑らかな濃淡（濃度文字の段階が主役）
    "shapes": _shapes,      # 幾何図形（はっきりした輪郭）
    "edges": _edges,        # 高周波（エッジ文字が主役）
    "silhouette": _vignette,# 明暗のコントラストが大きい構図
}


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="合成入力画像を生成する")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "synth")
    ap.add_argument("--size", default="800x600")
    args = ap.parse_args()

    w, h = (int(v) for v in args.size.lower().split("x"))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, fn in BUILDERS.items():
        arr = (np.clip(fn(w, h), 0.0, 1.0) * 255).round().astype(np.uint8)
        path = args.out / f"{name}.png"
        Image.fromarray(arr, mode="L").convert("RGB").save(path)
        print(f"saved: {path}")


if __name__ == "__main__":
    main()
