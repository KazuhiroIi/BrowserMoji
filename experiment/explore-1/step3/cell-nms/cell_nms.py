# -*- coding: utf-8 -*-
"""Step3 案5: セルレベル NMS (尾根検出).

強度マップをソースごとに作り、16px セルごとの最大値が
近傍(半径2セル)での局所最大(尾根)かつ下限閾値以上のセルをエッジマスとする。
 - canny-low50 / edp: 二値化(>128) → 距離変換(エッジ幅の太さ=尾根の高さ)
   → 尾根 = 太いエッジ領域の中心線(細線化効果)
 - xdog: 階調画像をそのまま強度として使用(正規化)
"""
import os
import glob
import numpy as np
import cv2

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data"
STEP2 = os.path.join(os.path.dirname(os.path.dirname(BASE)), "step2")
OUT = os.path.join(BASE, "out")
MONTAGE = os.path.join(BASE, "montage")

CELL = 16
NEIGHBOR_R = 2  # 近傍半径(セル単位, Chebyshev)

SOURCES = {
    "canny-low50": dict(
        dir=os.path.join(STEP2, "canny-improved", "out", "bilateral-low50-clean"),
        mode="binary",
        min_val=1.0,   # dist<1.0 は孤立ノイズ扱い(幅1エッジは dist=1)
    ),
    "edp": dict(
        dir=os.path.join(STEP2, "edge-drawing", "out", "edp-default"),
        mode="binary",
        min_val=1.0,
    ),
    "xdog": dict(
        dir=os.path.join(STEP2, "xdog", "out", "xdog-standard"),
        mode="gray",
        min_val=40.0,  # 弱い階調はフィラー扱い
    ),
}


def load_original(path, max_w=1280):
    img = cv2.imread(path)
    if img is None:
        raise IOError(path)
    h, w = img.shape[:2]
    if max(h, w) > max_w:
        if w >= h:
            img = cv2.resize(img, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)
        else:
            img = cv2.resize(img, (int(w * max_w / h), max_w), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray


def strength_map(edge_img, mode):
    """強度マップ float32 (0..255)."""
    if edge_img.ndim == 3:
        edge_img = cv2.cvtColor(edge_img, cv2.COLOR_BGR2GRAY)
    if mode == "binary":
        mask = (edge_img > 128).astype(np.uint8)
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        return dist.astype(np.float32)
    else:  # gray (xdog)
        s = edge_img.astype(np.float32)
        m = s.max()
        if m > 1e-6:
            s = s / m * 255.0
        return s


def cell_maxes(S):
    """セルごとの最大強度マップ (Hc, Wc)."""
    H, W = S.shape
    Hc, Wc = (H + CELL - 1) // CELL, (W + CELL - 1) // CELL
    pad_h, pad_w = Hc * CELL - H, Wc * CELL - W
    if pad_h or pad_w:
        S = np.pad(S, ((0, pad_h), (0, pad_w)), mode="constant")
    blocks = S.reshape(Hc, CELL, Wc, CELL)
    return blocks.max(axis=(1, 3)), Hc, Wc


def nms_cells(C, r, min_val):
    """セル強度 C について半径 r の近傍で局所最大かつ min_val 以上のセルを返す (bool)."""
    Hc, Wc = C.shape
    # 各セルについて近傍 (2r+1)^2 内の最大値
    pad = np.pad(C, r, mode="constant", constant_values=-1.0)
    local_max = np.full((Hc, Wc), -1.0, dtype=np.float32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            local_max = np.maximum(local_max, pad[r + dy:r + dy + Hc, r + dx:r + dx + Wc])
    return (C >= local_max - 1e-6) & (C >= min_val)


def render(gray, edge_cells, Hc, Wc):
    """エッジマス=白, フィラーマス=元画像セル平均輝度の 16px 矩形塗り."""
    H, W = gray.shape
    canvas = np.zeros((Hc * CELL, Wc * CELL), dtype=np.uint8)
    for cy in range(Hc):
        for cx in range(Wc):
            y0, x0 = cy * CELL, cx * CELL
            if edge_cells[cy, cx]:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = 255
            else:
                cell = gray[y0:min(y0 + CELL, H), x0:min(x0 + CELL, W)]
                canvas[y0:y0 + CELL, x0:x0 + CELL] = int(cell.mean()) if cell.size else 0
    return canvas[:H, :W]


def process():
    files = sorted(
        [f for f in glob.glob(os.path.join(DATA, "*.jpg")) + glob.glob(os.path.join(DATA, "*.png"))]
    )
    print(f"input files: {len(files)}")
    os.makedirs(MONTAGE, exist_ok=True)
    counts = {v: 0 for v in SOURCES}
    edge_ratio = {v: [] for v in SOURCES}
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        src, gray = load_original(path)
        H, W = gray.shape
        results = {}
        for v, cfg in SOURCES.items():
            edge_img = cv2.imread(os.path.join(cfg["dir"], name + ".jpg"), cv2.IMREAD_GRAYSCALE)
            if edge_img is None:
                raise IOError(cfg["dir"] + "/" + name)
            if edge_img.shape[:2] != (H, W):
                edge_img = cv2.resize(edge_img, (W, H), interpolation=cv2.INTER_NEAREST)
            S = strength_map(edge_img, cfg["mode"])
            C, Hc, Wc = cell_maxes(S)
            ec = nms_cells(C, NEIGHBOR_R, cfg["min_val"])
            vis = render(gray, ec, Hc, Wc)
            outdir = os.path.join(OUT, v)
            os.makedirs(outdir, exist_ok=True)
            cv2.imwrite(os.path.join(outdir, name + ".jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
            results[v] = vis
            counts[v] += 1
            edge_ratio[v].append(ec.mean())

        # montage: original + 3 sources, labeled
        h, w = gray.shape
        scale = 480.0 / h
        tw = max(1, int(w * scale))
        tiles = []
        for label, im in [("original", src)] + [(v, cv2.cvtColor(results[v], cv2.COLOR_GRAY2BGR)) for v in SOURCES]:
            t = cv2.resize(im, (tw, 480), interpolation=cv2.INTER_AREA if im.shape[0] > 480 else cv2.INTER_CUBIC)
            tile = t.copy()
            cv2.rectangle(tile, (0, 0), (tw, 36), (0, 0, 0), -1)
            cv2.putText(tile, label, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            tiles.append(tile)
        montage = np.hstack(tiles)
        cv2.imwrite(os.path.join(MONTAGE, name + ".jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
        ratios = "  ".join(f"{v}={edge_ratio[v][-1]*100:.1f}%" for v in SOURCES)
        print(f"done: {name}  edge cells: {ratios}")
    print("counts:", counts)


if __name__ == "__main__":
    process()
