"""グリフアトラス + 特徴量テーブルの生成（architecture.md §4 の基準実装）。

各文字を正方形セル（既定 64×64px）に描画し、
  - out/assets/atlas.png          : グリフアトラス（白背景・黒文字、16 列グリッド）
  - out/assets/features.json      : 特徴量テーブル（契約①スキーマ）
を出力する。特徴量はアトラス画像を feature_px（既定 16×16）に縮小したものから計算する。

使い方:
    uv run python atlas.py [--cell 64] [--fs 16] [--charset all] [--font fonts/NotoSansJP-Regular.otf]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import charset
import config
import glyphfeat

HERE = Path(__file__).resolve().parent
DEFAULT_FONT = HERE / "fonts" / "NotoSansJP-Regular.otf"
OUT_ASSETS = HERE / "out" / "assets"


def glyph_coverage(font_path: Path, chars: list[str]) -> tuple[list[str], list[str]]:
    """フォントが収録している文字 / していない文字に分ける。"""
    from fontTools.ttLib import TTFont

    tt = TTFont(str(font_path), fontNumber=0)
    cmap = tt.getBestCmap()
    have, missing = [], []
    for ch in chars:
        (have if ord(ch) in cmap else missing).append(ch)
    return have, missing


def render_glyph(font: ImageFont.FreeTypeFont, ch: str, cell: int) -> np.ndarray:
    """1 文字を cell×cell（白背景・黒文字）に描画し、インク率 0..1 の配列を返す。"""
    img = Image.new("L", (cell, cell), 255)
    draw = ImageDraw.Draw(img)
    if ch != "　":  # 全角スペースは描かない
        draw.text((cell / 2, cell / 2), ch, font=font, fill=0, anchor="mm")
    ink = 1.0 - np.asarray(img, dtype=np.float32) / 255.0
    return ink


def build(font_path: Path, cell: int, fs: int, preset: str) -> tuple[Image.Image, dict]:
    if not font_path.exists():
        sys.exit(f"font not found: {font_path}（README の手順で fonts/ に配置してください）")

    entries = charset.preset_chars(preset)
    all_chars = [c for _, c, _ in entries]
    have, missing = glyph_coverage(font_path, sorted(set(all_chars)))
    if missing:
        print("WARNING: フォント未収録のため除外する文字: " + " ".join(f"{c}(U+{ord(c):04X})" for c in missing))
    have_set = set(have)

    font = ImageFont.truetype(str(font_path), size=cell)
    norms = glyphfeat.dol_normalizations(fs)

    atlas_cols = config.ATLAS_COLS
    chars = [e for e in entries if e[1] in have_set]
    atlas_rows = (len(chars) + atlas_cols - 1) // atlas_cols
    atlas = Image.new("L", (atlas_cols * cell, atlas_rows * cell), 255)

    records = []
    for idx, (group, ch, sub) in enumerate(chars):
        ink64 = render_glyph(font, ch, cell)
        tile = Image.fromarray((255.0 * (1.0 - ink64)).round().astype(np.uint8), mode="L")
        atlas.paste(tile, ((idx % atlas_cols) * cell, (idx // atlas_cols) * cell))

        ink_fs = cv2.resize(ink64, (fs, fs), interpolation=cv2.INTER_AREA)
        density = float(ink_fs.mean())
        dir8 = glyphfeat.dir8_map(ink_fs, fs, norms).reshape(glyphfeat.N_DIR, -1).max(axis=1)
        region4 = (ink_fs.reshape(glyphfeat.REGION, fs // glyphfeat.REGION,
                                  glyphfeat.REGION, fs // glyphfeat.REGION)
                   .mean(axis=(1, 3))).reshape(-1)  # 行優先で 16 個
        records.append({
            "id": idx,
            "char": ch,
            "group": group,
            "subgroup": sub,
            "density": round(density, 6),
            "dir8": [round(float(v), 6) for v in dir8],
            "region4": [round(float(v), 6) for v in region4],
        })

    meta = {
        "schemaVersion": 1,
        "featureVersion": 1,
        "font": font_path.name,
        "fontLicense": "OFL-1.1",
        "charsetPreset": preset,
        "cellPx": cell,
        "featurePx": fs,
        "atlasCols": atlas_cols,
        "atlasRows": atlas_rows,
        "charCount": len(records),
        "directionsDeg": list(glyphfeat.DIRECTIONS_DEG),
        "regionGrid": [glyphfeat.REGION, glyphfeat.REGION],
        "counts": {g: sum(1 for r in records if r["group"] == g) for g in charset.groups()},
        "note": "id はアトラス内の位置（行優先）と一致する。density/dir8/region4 は 0..1。",
    }
    return atlas, {"meta": meta, "chars": records}


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="グリフアトラスと特徴量テーブルを生成する")
    ap.add_argument("--font", type=Path, default=DEFAULT_FONT)
    ap.add_argument("--cell", type=int, default=64, help="セルのpx（正方形）")
    ap.add_argument("--fs", type=int, default=16, help="特徴量計算用のセル内部解像度")
    ap.add_argument("--charset", default="all", choices=list(charset.CHARSET_PRESETS))
    ap.add_argument("--out", type=Path, default=OUT_ASSETS)
    args = ap.parse_args()

    atlas_img, data = build(args.font, args.cell, args.fs, args.charset)
    args.out.mkdir(parents=True, exist_ok=True)
    png_path = args.out / "atlas.png"
    json_path = args.out / "features.json"
    atlas_img.save(png_path)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    m = data["meta"]
    print(f"atlas: {png_path}  ({m['atlasCols']}x{m['atlasRows']} cells, {m['cellPx']}px)")
    print(f"features: {json_path}  ({m['charCount']} chars, counts={m['counts']})")


if __name__ == "__main__":
    main()
