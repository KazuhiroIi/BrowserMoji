"""濃度フィラー候補の計測（EXP-3 の補助ツール）。

charset.py の density 群（採用 27 段階、計測値 0.000〜0.937）に文字を
追加・比較するときの補助。atlas.py と同じ手順（64px 描画 → 16×16 へ
INTER_AREA 縮小 → 平均インク率）で計測するため、features.json の値と
直接比較できる。CANDIDATES は既存の density 群に含まれない候補プール
（フォント未収録の文字は自動で除外される）。

出力:
  - 標準出力: 濃度順の候補表（タグ付き、フォント未収録は除外して表示）
  - out/charset/proposal.png: 濃度順に並べた提案シート

使い方:
    uv run python scan.py
    uv run python scan.py --min 0.15 --max 0.75   # 表示を濃度で絞る
"""

from __future__ import annotations

import argparse
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import atlas
import config

HERE = atlas.HERE

# 候補プール（タグ → 文字列）。未収録文字は glyph_coverage が除外する。
# 既存 density 群にある文字（　・：∴◇○□△☆◎※▲◆★●■）は含めない。
CANDIDATES: dict[str, str] = {
    # ブロック要素・網かけ（碁盤状の陰影。幾何学的に濃度が揃う系列）
    "block": "▀▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕▘▝▖▗▚▞▙▟▛▜",
    # 半分だけ塗った図形（円・四角・象限）
    "half": "◐◓◑◒◔◕◧◨◩◪◰◳◲◴◵◶",
    # 塗り・枠の四角系（既存の □ ◇ ○ 系の濃い側の仲間）
    "square": "▪▫▭▮▯▰▱▢▣▤▥▦▧▨▩◼◻◽◾⬒⬓⬚⧫",
    # 円・星・ダイヤ系
    "circle": "◯◉◈◍⬤⬮⬯⊙⊚⊛⊜⊝⊖⊗⊘",
    "star": "✦✧✱✲✳✴✵✶✷✸✹✺✻✼✽✾❋❈❖❂✕✖✗✘✔✚✜✛",
    # その他の記号
    "misc": "∎∷∸⋰⋱⋈⋮⌗⌾⍟〓〶〄〒〠〆゛゜〇☰☱☲☳☴☵☶☷",
    # 全角記号（AA で定番の中間調フィラー）
    "punct": "＠＃＄％＆＊＋＝？！＿￣",
}


def main() -> None:
    config.force_utf8_stdio()
    ap = argparse.ArgumentParser(description="濃度フィラー候補を計測して提案シートを出す")
    ap.add_argument("--font", default=str(atlas.DEFAULT_FONT))
    ap.add_argument("--cell", type=int, default=64)
    ap.add_argument("--fs", type=int, default=16)
    ap.add_argument("--min", type=float, default=0.0, help="表示する濃度の下限")
    ap.add_argument("--max", type=float, default=1.01, help="表示する濃度の上限")
    args = ap.parse_args()

    font_path = atlas.Path(args.font)
    tags: list[str] = []
    chars: list[str] = []
    for tag, s in CANDIDATES.items():
        for ch in s:
            tags.append(tag)
            chars.append(ch)

    have, missing = atlas.glyph_coverage(font_path, sorted(set(chars)))
    if missing:
        print("フォント未収録（除外）: " + " ".join(f"{c}(U+{ord(c):04X})" for c in missing))
    have_set = set(have)

    font = ImageFont.truetype(str(font_path), size=args.cell)
    rows = []
    for ch, tag in zip(chars, tags):
        if ch not in have_set:
            continue
        ink = atlas.render_glyph(font, ch, args.cell)
        ink_fs = cv2.resize(ink, (args.fs, args.fs), interpolation=cv2.INTER_AREA)
        rows.append((float(ink_fs.mean()), ch, tag))

    rows.sort(key=lambda r: r[0])
    print(f"\n濃度順（{len(rows)} 文字、既存 density 群: 0.000〜0.640）:")
    for d, ch, tag in rows:
        if args.min <= d <= args.max:
            print(f"  {ch}  U+{ord(ch):04X}  {d:.3f}  [{tag}]")

    # 濃度順に並べた提案シート
    out_dir = HERE / "out" / "charset"
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = args.cell
    label_h = 22
    cols_n = min(len(rows), 16)
    rows_n = (len(rows) + 15) // 16
    img = Image.new("L", (cols_n * cell, rows_n * (cell + label_h)), 255)
    draw = ImageDraw.Draw(img)
    label_font = ImageFont.truetype(str(font_path), size=18)
    for i, (d, ch, tag) in enumerate(rows):
        x = (i % 16) * cell
        y = (i // 16) * (cell + label_h)
        ink = atlas.render_glyph(font, ch, cell)
        tile = Image.fromarray((255.0 * (1.0 - ink)).round().astype(np.uint8), mode="L")
        img.paste(tile, (x, y + label_h))
        draw.text((x + 4, y + 2), f"{ch}{d:.2f}", fill=90, font=label_font)
    path = out_dir / "proposal.png"
    img.save(path)
    print(f"提案シート: {path}")


if __name__ == "__main__":
    main()
