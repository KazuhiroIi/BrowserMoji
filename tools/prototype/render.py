"""選択結果（文字 id のグリッド）→ 画像の描画（基準実装）。

描画はアトラス PNG からタイルを転写するだけで行う
（実行時にフォントを開かない = Web 本番と同じ入出力の形）。
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def render_ascii(ids: np.ndarray, atlas: np.ndarray, atlas_cols: int, cell_px: int) -> Image.Image:
    """ids: (rows, cols) の文字 id → アトラスのタイルを貼って描画する。

    アトラスを (タイル数, cell_px, cell_px) に組み替えてから 1 回の
    高度参照（fancy indexing）で集める。実行時にフォントは開かない。
    """
    rows, cols = ids.shape
    atlas_rows = atlas.shape[0] // cell_px
    tiles = atlas.reshape(atlas_rows, cell_px, atlas_cols, cell_px).transpose(0, 2, 1, 3)
    tiles = np.ascontiguousarray(tiles).reshape(-1, cell_px, cell_px)  # (n_tiles, cp, cp)
    grid = tiles[ids]                                                  # (rows, cols, cp, cp)
    grid = grid.transpose(0, 2, 1, 3).reshape(rows * cell_px, cols * cell_px)
    return Image.fromarray(grid, mode="L")


def labeled(img: Image.Image, label: str, font_path, bar_h: int = 30) -> Image.Image:
    """上部にラベル帯を付けた画像を返す。"""
    w, h = img.size
    canvas = Image.new("L", (w, h + bar_h), 255)
    canvas.paste(img, (0, bar_h))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(str(font_path), size=20)
    except Exception:
        font = None
    draw.text((8, 4), label, fill=0, font=font)
    return canvas


def comparison(panels: list[tuple[str, Image.Image]], font_path, max_w: int = 1600) -> Image.Image:
    """(ラベル, 画像) の縦並び比較図を作る。画像はすべて 1 枚目のサイズに合わせる。"""
    w0, h0 = panels[0][1].size
    bar_h, gap = 30, 6
    total_h = sum(h0 + bar_h for _, im in panels) + gap * (len(panels) - 1)
    canvas = Image.new("L", (w0, total_h), 128)
    y = 0
    for label, im in panels:
        if im.size != (w0, h0):
            im = im.resize((w0, h0), Image.LANCZOS)
        canvas.paste(labeled(im, label, font_path, bar_h), (0, y))
        y += h0 + bar_h + gap
    if w0 > max_w:
        scale = max_w / w0
        canvas = canvas.resize((max_w, round(total_h * scale)), Image.LANCZOS)
    return canvas
