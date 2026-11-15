"""Web 実装の 2 つのパイプライン（classic / selectorA）を Python で再実装し、
段階ごとの中間出力を画像として保存する。

対象: src/pipeline の TS 実装（2026-11-15 時点、076886d + モード切替）。
対応関係:

  Web (TS)                          本スクリプト
  ---------------------------------  ---------------------------------
  config.ts defaultConfig /          MODE_PARAMS
    modeDefaults / effectiveFeaturePx
  grid.ts computeGrid                compute_grid
  preprocess.ts sampleFrame          sample_frame（cover 切り出し + 縮小）
  featureExtractor.ts                extract_features（Sobel + セル集約）
    CpuFeatureExtractor
  glyphSelector.ts                   select_classic / select_selector_a
    ClassicGlyphSelector
    DensityEdgeGlyphSelector
  atlas.ts DummyAtlasProvider        measure_ink（ink 実測）+ 文字セット定義
  renderer.ts Canvas2DRenderer 相当  render_ascii（フォントで直接描画）

使い方:
    tools/prototype/.venv/Scripts/python.exe web_pipeline_sim.py
    （--image / --cols-classic / --cols-selectora などで上書き可能）

出力（out/<mode>/ 配下）:
    00_input_cover.png      cover 切り出し後の入力
    01_preprocessed.png     前処理後のフレーム（cols×fs × rows×fs の輝度）
    02_cell_luminance.png   セル平均輝度（①特徴量 luminance）
    03_cell_gradmax.png     セル内最大 |Sobel|（②特徴量 gradMagnitude）
    04_cell_coherence.png   勾配整合性（selectorA のみ。D-009）
    05_edge_mask.png        エッジ置換対象セル（しきい値 + 整合性を満たすセル）
    06_ascii_render.png     最終描画結果（Canvas2DRenderer 相当）
    ascii.txt               選択された文字のテキスト
    out/comparison.png      両モードの最終結果の比較図
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_IMAGE = ROOT / "data" / "scene2.jpg"
DEFAULT_FONT = ROOT / "tools" / "prototype" / "fonts" / "NotoSansJP-Regular.otf"
OUT_DIR = HERE / "out"

# --- 文字セット（src/pipeline/atlas.ts と同じ定義） ----------------------------

# EXP-3 採用セット（D-010 / T-4）: density 27 + line 35 = 62 文字
DENSITY_CHARS_ALL = [
    "　", "・", "：", "∴", "◇", "○", "□", "△", "☆", "◎", "※",
    "▒", "▣", "★", "▃", "◐", "▲", "▄", "◆", "▀", "▅", "●", "■",
    "▆", "▛", "▇", "█",
]
LINE_CHARS_ALL = [
    "―", "─", "━", "│", "┃", "┌", "┐", "└", "┘",
    "├", "┤", "┬", "┴", "┼", "┏", "┓", "┗", "┛",
    "┣", "┫", "┳", "┻", "╋", "═", "║", "╭", "╮", "╯", "╰",
    "╱", "╲", "╳", "／", "＼", "｜",
]

# classic（076886d 適用前）のダミーセット: density 9 + line 4 = 13 文字
LEGACY_DENSITY_CHARS = ["　", "・", "○", "＋", "の", "三", "日", "◎", "■"]
LEGACY_LINE_CHARS = ["―", "／", "｜", "＼"]

# selectorA のエッジ置換候補（まっすぐな線のみ。角・T 字は向きが一意でない。D-009 / T-5）
STRAIGHT_LINES: list[tuple[str, int]] = [
    ("―", 0), ("─", 0), ("━", 0), ("═", 0),      # 水平
    ("│", 90), ("┃", 90), ("║", 90), ("｜", 90),  # 垂直
    ("╲", 45), ("＼", 45),                        # バックスラッシュ
    ("╱", 135), ("／", 135),                      # スラッシュ
]

# 4 方向の線（classic 用。lineIds の定義と同じ文字）
LINE_ID_CHARS = {"horizontal": "―", "vertical": "｜", "slash": "／", "backslash": "＼"}

# --- モードごとのパラメータ（config.ts の既定値に対応） -----------------------

MODE_PARAMS: dict[str, dict] = {
    # 076886d 適用前の値
    "classic": dict(
        columns=48, contrast=1.0, edge_threshold=0.2, edge_priority=0.5,
        feature_px=1, coherence_min=None, charset="default",
    ),
    # EXP-2 / EXP-3 の適用値（D-009 / D-010）
    "selectorA": dict(
        columns=100, contrast=1.0, edge_threshold=0.14, edge_priority=0.5,
        feature_px=16, coherence_min=0.25, charset="all",
    ),
}

CANVAS_WIDTH = 1200          # 出力 canvas の幅の想定（px）
ATLAS_CELL = 96              # アトラス計測用セル（atlas.ts の ATLAS_CELL に相当）
INK_MEASURE_PX = 64          # ink 実測の描画サイズ（atlas.ts measureInk と同じ）
FONT_RATIO = 0.86            # セルに対するフォントサイズ比（drawGlyphCell と同じ）


# --- グリッド計算（grid.ts computeGrid） --------------------------------------

def compute_grid(canvas_w: int, canvas_h: int, columns: int, feature_px: int) -> dict:
    cols = max(1, int(columns))
    cell_w = canvas_w / cols
    cell_h = cell_w  # 正方形のセル（T-2）
    rows = max(1, int(canvas_h / cell_h))
    return dict(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                feature_px=max(1, round(feature_px)))


# --- 前処理（preprocess.ts sampleFrame） ---------------------------------------

def sample_frame(img: Image.Image, grid: dict) -> Image.Image:
    """cover で切り出して cols×fs × rows×fs に縮小する（drawImage 縮小に相当）。"""
    fs = grid["feature_px"]
    width = grid["cols"] * fs
    height = grid["rows"] * fs
    vw, vh = img.size
    scale = max(width / vw, height / vh)
    sw, sh = width / scale, height / scale
    sx, sy = (vw - sw) / 2, (vh - sh) / 2
    # cover 切り出し（中央トリミング）+ 縮小。縮小は INTER_AREA が平均に相当する
    return img.resize((width, height), Image.Resampling.LANCZOS,
                      box=(sx, sy, sx + sw, sy + sh))


# --- 特徴量抽出（featureExtractor.ts CpuFeatureExtractor） ---------------------

def extract_features(pre: Image.Image, grid: dict) -> dict:
    """BT.601 輝度 + Sobel。セルごとに 4 値（luminance / gradMagnitude / gradAngle / coherence）。"""
    fs = grid["feature_px"]
    rows, cols = grid["rows"], grid["cols"]
    rgb = np.asarray(pre.convert("RGB"), dtype=np.float32) / 255.0
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])

    # Sobel（端は座標をクランプ = edge リプリケートパッド。TS の at() と同じ）
    p = np.pad(lum, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    mag = np.hypot(gx, gy) / 4.0  # 0..1 輝度で最大 |gx| = 4

    # セル集約（cx = floor(x / fs)）
    def block(v, op):
        v = v[: rows * fs, : cols * fs].reshape(rows, fs, cols, fs)
        return v.max(axis=(1, 3)) if op == "max" else v.sum(axis=(1, 3))

    block_area = fs * fs
    sum_lum = block(lum, "sum")
    max_mag = block(mag, "max")
    sum_mag = block(mag, "sum")
    sum_vx = block(gx, "sum") / (block_area * 4.0)  # 平均勾配ベクトル（4 で正規化）
    sum_vy = block(gy, "sum") / (block_area * 4.0)

    vec_len = np.hypot(sum_vx, sum_vy)
    mean_mag = sum_mag / block_area
    return dict(
        luminance=sum_lum / block_area,
        grad_magnitude=max_mag,
        grad_angle=np.arctan2(sum_vy, sum_vx),
        grad_coherence=np.minimum(1.0, vec_len / (mean_mag + 1e-6)),
    )


# --- ink 実測（atlas.ts measureInk / drawGlyphCell） ---------------------------

def measure_ink(chars: list[str], font_path: Path) -> np.ndarray:
    """各文字を 64×64 で描いて ink（平均インク率 0..1、1 = 黒に近い）を実測する。"""
    size = INK_MEASURE_PX
    font = ImageFont.truetype(str(font_path), size=int(size * FONT_RATIO))
    out = np.empty(len(chars), dtype=np.float32)
    for i, ch in enumerate(chars):
        img = Image.new("L", (size, size), 255)
        draw = ImageDraw.Draw(img)
        if ch != "　":  # 全角スペースは描かない
            draw.text((size / 2, size / 2), ch, font=font, fill=0, anchor="mm")
        out[i] = 1.0 - np.asarray(img, dtype=np.float32).mean() / 255.0
    return out


# --- 文字選択: classic（glyphSelector.ts ClassicGlyphSelector） ----------------

def select_classic(feat: dict, density_ids: np.ndarray, line_ids4: dict[str, int],
                   params: dict) -> np.ndarray:
    """輝度の等分量子化で濃度文字を選び、しきい値以上のセルを 4 方向の線へ置換する。

    density_ids: ink 昇順の濃度グリフ ID。line_ids4: 方向名 → 線グリフ ID
    （atlas.ts の lineIds に対応）。
    """
    lum = feat["luminance"]
    v = np.clip((lum - 0.5) * params["contrast"] + 0.5, 0.0, 1.0)
    # 等分量子化: round(v × (n−1)) を densityIds（薄い順）へのインデックスに使う
    idx = np.clip(np.round(v * (len(density_ids) - 1)).astype(np.int64), 0, len(density_ids) - 1)
    ids = density_ids[idx]

    eff = params["edge_threshold"] * (1.5 - min(1.0, max(0.0, params["edge_priority"])))
    use = feat["grad_magnitude"] >= eff
    if use.any():
        ids = _replace_line4(ids, feat["grad_angle"], use, line_ids4)
    return ids


def _replace_line4(ids: np.ndarray, grad_angle: np.ndarray, use: np.ndarray,
                   line_ids4: dict[str, int]) -> np.ndarray:
    """勾配 + 90° の向きに最も近い 4 方向の線文字へ置換する（pickLineGlyph4）。"""
    ang = np.mod(grad_angle[use] + np.pi / 2, np.pi)  # 0..π に正規化
    cand = [(0.0, "horizontal"), (45.0, "backslash"),
            (90.0, "vertical"), (135.0, "slash")]
    replaced = ids[use].copy()
    for k, a in enumerate(ang):
        deg = np.degrees(a)
        best_name, best_d = None, np.inf
        for cdeg, name in cand:
            d = abs(deg - cdeg)
            d = min(d, 180.0 - d)
            if d < best_d:
                best_d, best_name = d, name
        replaced[k] = line_ids4[best_name]
    ids[use] = replaced
    return ids


# --- 文字選択: selectorA（glyphSelector.ts DensityEdgeGlyphSelector / D-009） ---

def select_selector_a(feat: dict, density_ids: np.ndarray, density_ink: np.ndarray,
                      straight_lines: list[tuple[int, float, float]], params: dict) -> np.ndarray:
    """計測濃度の最近傍 + セル内最大 |Sobel| + 整合性 + 向き・太さスコア式。

    straight_lines: [(グリフ ID, 向き deg, ink), ...]（atlas.ts の straightLines に対応）。
    """
    lum = feat["luminance"]
    v = np.clip((lum - 0.5) * params["contrast"] + 0.5, 0.0, 1.0)

    # 濃度選択: 目標 ink（1 − 輝度）との最近傍（searchsorted 相当）
    ink_level = np.clip(1.0 - v, 0.0, 1.0).ravel()
    pos = np.clip(np.searchsorted(density_ink, ink_level), 1, len(density_ink) - 1)
    lo, hi = pos - 1, pos
    take_lo = np.abs(ink_level - density_ink[lo]) <= np.abs(ink_level - density_ink[hi])
    ids = density_ids[np.where(take_lo, lo, hi)].reshape(lum.shape)

    # エッジ判定: セル内最大 |Sobel| + 整合性（D-009）
    eff = params["edge_threshold"] * (1.5 - min(1.0, max(0.0, params["edge_priority"])))
    use = (feat["grad_magnitude"] >= eff) & (feat["grad_coherence"] >= params["coherence_min"])
    if use.any():
        replace_line_scored(ids, feat["grad_angle"], feat["grad_magnitude"], use, straight_lines)
    return ids


def replace_line_scored(ids: np.ndarray, grad_angle: np.ndarray, grad_mag: np.ndarray,
                        use: np.ndarray, straight_lines: list[tuple[int, float, float]]) -> None:
    """score = (Δangle / (π/8))² + 0.5 · (line.ink − target)² で最小の直線を選ぶ（pickLineGlyph）。"""
    ang = np.mod(grad_angle[use] + np.pi / 2, np.pi)  # 線の向き 0..π
    target = np.clip(grad_mag[use], 0.0, 1.0)          # 弱いエッジ → 細い（薄い）線
    line_ids = np.array([g for g, _, _ in straight_lines])
    angles = np.radians(np.array([a for _, a, _ in straight_lines], dtype=np.float32))
    inks = np.array([k for _, _, k in straight_lines], dtype=np.float32)
    d = np.abs(ang[:, None] - angles[None, :])
    d = np.minimum(d, np.pi - d)  # 折り返し
    score = (d / (np.pi / 8.0)) ** 2 + 0.5 * (inks[None, :] - target[:, None]) ** 2
    ids[use] = line_ids[np.argmin(score, axis=1)]


# --- 描画（renderer.ts Canvas2DRenderer 相当） ---------------------------------

def render_ascii(ids: np.ndarray, char_of: dict[int, str], ink_by_char: dict[str, float],
                 grid: dict, canvas_w: int, font_path: Path) -> Image.Image:
    """文字グリッド → 出力 canvas への描画（白背景 + 黒文字、T-3 / T-6）。"""
    cols, rows = grid["cols"], grid["rows"]
    cell = canvas_w / cols
    canvas_h = round(cell * rows)
    img = Image.new("L", (canvas_w, canvas_h), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(font_path), size=max(1, int(cell * FONT_RATIO)))
    for y in range(rows):
        for x in range(cols):
            ch = char_of[int(ids[y, x])]
            if ink_by_char.get(ch, 0.0) < 0.01:  # ほぼ空白（全角スペース等）はスキップ
                continue
            cx, cy = round((x + 0.5) * cell), round((y + 0.5) * cell)
            draw.text((cx, cy), ch, font=font, fill=0, anchor="mm")
    return img


# --- ユーティリティ -------------------------------------------------------------

def to_u8(a: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(a, 0.0, 1.0) * 255).round().astype(np.uint8), mode="L")


def upscale_cellmap(cellmap: np.ndarray, fs: int) -> Image.Image:
    """rows×cols のセルマップを各セル fs×fs に引き伸ばして可視化する。"""
    img = to_u8(cellmap)
    return img.resize((img.width * fs, img.height * fs), Image.Resampling.NEAREST)


def labeled(img: Image.Image, label: str, font_path: Path, bar_h: int = 30) -> Image.Image:
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


def comparison(panels: list[tuple[str, Image.Image]], font_path: Path, max_w: int = 1600) -> Image.Image:
    w0, h0 = panels[0][1].size
    bar_h, gap = 30, 6
    total_h = sum(h0 + bar_h for _, _ in panels) + gap * (len(panels) - 1)
    canvas = Image.new("L", (w0, total_h), 128)
    y = 0
    for label, im in panels:
        if im.size != (w0, h0):
            im = im.resize((w0, h0), Image.Resampling.LANCZOS)
        canvas.paste(labeled(im, label, font_path, bar_h), (0, y))
        y += h0 + bar_h + gap
    if w0 > max_w:
        canvas = canvas.resize((max_w, round(total_h * max_w / w0)), Image.Resampling.LANCZOS)
    return canvas


# --- 1 モードの実行 -------------------------------------------------------------

def run_mode(mode: str, img: Image.Image, font_path: Path, out_root: Path,
             cols_override: int | None, canvas_w: int) -> dict:
    params = MODE_PARAMS[mode]
    cols = cols_override or params["columns"]
    fs = params["feature_px"]

    # グリッド計算（computeGrid）
    canvas_h = round(canvas_w * img.height / img.width)
    grid = compute_grid(canvas_w, canvas_h, cols, fs)

    # 文字セットと ink 実測
    if params["charset"] == "default":
        density_chars, line_chars = LEGACY_DENSITY_CHARS, LEGACY_LINE_CHARS
    else:
        density_chars, line_chars = DENSITY_CHARS_ALL, LINE_CHARS_ALL
    all_chars = list(dict.fromkeys(density_chars + line_chars))  # 重複をまとめる
    ink = measure_ink(all_chars, font_path)
    ink_by_char = dict(zip(all_chars, ink.tolist()))

    # 文字選択・描画で共有するアトラス情報（atlas.ts buildDummyAtlas に対応）
    id_of_char = {ch: i for i, ch in enumerate(all_chars)}
    char_of = {i: ch for i, ch in enumerate(all_chars)}
    # densityIds: ink 昇順（薄い順）の濃度グリフ ID
    ink_density = np.array([ink_by_char[c] for c in density_chars], dtype=np.float32)
    density_ids = np.array([id_of_char[c] for c in density_chars])[np.argsort(ink_density)]
    # lineIds（classic 用の 4 方向）と straightLines（selectorA 用）
    line_ids4 = {name: id_of_char[ch] for name, ch in LINE_ID_CHARS.items()}
    straight_lines = [(id_of_char[ch], float(deg), float(ink_by_char[ch]))
                      for ch, deg in STRAIGHT_LINES if ch in id_of_char]

    # ① 前処理 → ② 特徴量抽出
    pre = sample_frame(img, grid)
    feat = extract_features(pre, grid)

    # ③ 文字選択
    if mode == "classic":
        ids = select_classic(feat, density_ids, line_ids4, params)
    else:
        ids = select_selector_a(feat, density_ids, ink_density[np.argsort(ink_density)],
                                straight_lines, params)

    # ④ 描画
    rendered = render_ascii(ids, char_of, ink_by_char, grid, canvas_w, font_path)

    # --- 中間出力 ---
    out = out_root / mode
    out.mkdir(parents=True, exist_ok=True)
    fs_eff = grid["feature_px"]

    # 00: cover 切り出し後の入力（グリッドと同じアスペクト）
    cover_w, cover_h = grid["cols"] * 8, grid["rows"] * 8  # 見やすい解像度に
    vw, vh = img.size
    scale = max(cover_w / vw, cover_h / vh)
    sw, sh = cover_w / scale, cover_h / scale
    sx, sy = (vw - sw) / 2, (vh - sh) / 2
    img.resize((cover_w, cover_h), Image.Resampling.LANCZOS,
               box=(sx, sy, sx + sw, sy + sh)).convert("RGB").save(out / "00_input_cover.png")

    # 01: 前処理後のフレーム（cols×fs × rows×fs の輝度）
    to_u8(_lum_of(pre)).save(out / "01_preprocessed.png")

    # 02-05: セル単位の特徴量マップ（各セルを fs×fs に引き伸ばして可視化）
    upscale_cellmap(feat["luminance"], fs_eff).save(out / "02_cell_luminance.png")
    upscale_cellmap(feat["grad_magnitude"], fs_eff).save(out / "03_cell_gradmax.png")
    if mode == "selectorA":
        upscale_cellmap(feat["grad_coherence"], fs_eff).save(out / "04_cell_coherence.png")

    # 05: エッジ置換対象セル（白 = 対象）
    eff = params["edge_threshold"] * (1.5 - min(1.0, max(0.0, params["edge_priority"])))
    mask = feat["grad_magnitude"] >= eff
    if mode == "selectorA":
        mask &= feat["grad_coherence"] >= params["coherence_min"]
    upscale_cellmap(mask.astype(np.float32), fs_eff).save(out / "05_edge_mask.png")

    # 06 / ascii.txt: 最終結果
    rendered.save(out / "06_ascii_render.png")
    text = "\n".join("".join(char_of[int(ids[y, x])] for x in range(grid["cols"]))
                     for y in range(grid["rows"]))
    (out / "ascii.txt").write_text(text + "\n", encoding="utf-8")

    print(f"[{mode}] cols={grid['cols']} rows={grid['rows']} featurePx={fs_eff} "
          f"chars={len(all_chars)} -> {out}")
    return dict(rendered=rendered, text=text)


def _lum_of(pre: Image.Image) -> np.ndarray:
    rgb = np.asarray(pre.convert("RGB"), dtype=np.float32) / 255.0
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Web パイプライン（classic / selectorA）の Python 再実装")
    ap.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    ap.add_argument("--font", type=Path, default=DEFAULT_FONT)
    ap.add_argument("--canvas-w", type=int, default=CANVAS_WIDTH)
    ap.add_argument("--cols-classic", type=int, default=None)
    ap.add_argument("--cols-selectora", type=int, default=None)
    args = ap.parse_args()

    if not args.font.exists():
        sys.exit(f"font not found: {args.font}")
    img = Image.open(args.image).convert("RGB")

    results = {}
    for mode, cols_key in (("classic", "cols_classic"), ("selectorA", "cols_selectora")):
        results[mode] = run_mode(mode, img, args.font, OUT_DIR,
                                 getattr(args, cols_key), args.canvas_w)

    # 比較図（両モードの最終結果を縦に並べる）
    panels = [
        (f"classic (cols={MODE_PARAMS['classic']['columns']})", results["classic"]["rendered"]),
        (f"selectorA (cols={MODE_PARAMS['selectorA']['columns']})", results["selectorA"]["rendered"]),
        ("input", Image.open(args.image).convert("L")),
    ]
    comparison(panels, args.font).save(OUT_DIR / "comparison.png")
    print(f"comparison -> {OUT_DIR / 'comparison.png'}")


if __name__ == "__main__":
    main()
