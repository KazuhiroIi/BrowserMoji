"""文字セット群ごとのシート画像（EXP-3 の資料）。

アトラスから群ごとに切り出し、各文字の計測濃度を,label として並べた PNG を
out/charset/<group>.png に出力する。

使い方:
    uv run python sheet.py [--charset all]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import charset
import config

HERE = Path(__file__).resolve().parent


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="群ごとの文字シートを生成する")
    ap.add_argument("--charset", default="all", choices=list(charset.CHARSET_PRESETS))
    ap.add_argument("--assets", type=Path, default=HERE / "out" / "assets")
    ap.add_argument("--out", type=Path, default=HERE / "out" / "charset")
    args = ap.parse_args()

    data = json.loads((args.assets / "features.json").read_text(encoding="utf-8"))
    meta = data["meta"]
    if meta["charsetPreset"] != args.charset:
        raise SystemExit(f"features.json は charset={meta['charsetPreset']} で生成されています。")
    cell = meta["cellPx"]
    atlas_cols = meta["atlasCols"]
    atlas = Image.open(args.assets / "atlas.png").convert("L")

    font = ImageFont.truetype(str(HERE / "fonts" / "NotoSansJP-Regular.otf"), size=18)
    label_h = 22

    # 群ごとに id をまとめる（連続している前提だが、一般形で扱う）
    by_group: dict[str, list[dict]] = {}
    for r in data["chars"]:
        by_group.setdefault(r["group"], []).append(r)

    args.out.mkdir(parents=True, exist_ok=True)
    for group, records in by_group.items():
        n = len(records)
        cols_n = min(n, atlas_cols)
        rows_n = (n + atlas_cols - 1) // atlas_cols
        img = Image.new("L", (cols_n * cell, rows_n * (cell + label_h)), 255)
        draw = ImageDraw.Draw(img)
        for i, r in enumerate(records):
            x = (i % atlas_cols) * cell
            y = (i // atlas_cols) * (cell + label_h)
            sx = (r["id"] % atlas_cols) * cell
            sy = (r["id"] // atlas_cols) * cell
            img.paste(atlas.crop((sx, sy, sx + cell, sy + cell)), (x, y + label_h))
            draw.text((x + 4, y + 2), f"{r['char']} {r['density']:.2f}", fill=90, font=font)
        path = args.out / f"{group}.png"
        img.save(path)
        densities = [r["density"] for r in records]
        print(f"{group:10s}: {n:3d} chars  density {min(densities):.3f}..{max(densities):.3f}  -> {path}")


if __name__ == "__main__":
    main()
