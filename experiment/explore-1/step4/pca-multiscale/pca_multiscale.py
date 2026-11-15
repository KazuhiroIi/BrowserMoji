"""Step4 案B: pca-multiscale — PCA 形状判定の多スケール化。

step3 の PCA 判定(16px セル, σ2/σ1<0.25)は「緩く曲がる輪郭を1セル内の
2次元分散に見て取りこぼす」弱点がある。そこで:

1. 4px 小セルで PCA 判定(σ2/σ1 < 0.4 と緩め)→ 16px セル内の小セル線率を計算
2. 16px 判定: 小セル線率 > 0.5 → 16px で線
   32px 窓判定: 窓全体のエッジ画素に PCA(σ2/σ1 < 0.4)→ 32px でも線
   - "ms-any": 16px か 32px のどちらかで線なら採用(輪郭拾い重視)
   - "ms-all": 両方で線なら採用(ノイズ抑止重視)

出力:
  step4/pca-multiscale/out/{ms-any|ms-all}/{stem}.jpg
  step4/pca-multiscale/montage/{stem}.jpg  (original + step3 pca-canny + ms-any + ms-all)
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
EXPL = ROOT.parent.parent
DATA_DIR = EXPL.parent.parent / "data"
EDGE_DIR = EXPL / "step2" / "canny-improved" / "out" / "bilateral-low50-clean"
STEP3_CANNY_DIR = EXPL / "step3" / "pca-shape" / "out" / "canny-low50"
OUT_DIR = ROOT / "out"
MONTAGE_DIR = ROOT / "montage"

MAX_SIDE = 1280
CELL = 16
SUB = 4
SUB_RATIO_TH = 0.4       # 4px 小セルの分散比しきい値(緩め)
SUB_MIN_PX = 3
SUB_RATE_TH = 0.5        # 16px セル内の小セル線率しきい値
BIG_RATIO_TH = 0.4       # 32px 窓の分散比しきい値
BIG_MIN_PX = 60          # 32px 窓の最小エッジ画素数


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def pca_ratio(pts: np.ndarray) -> float:
    pts = pts - pts.mean(axis=0)
    cov = pts.T @ pts / pts.shape[0]
    evals = np.linalg.eigvalsh(cov)  # ascending
    sigma1 = float(np.sqrt(max(evals[1], 1e-12)))
    sigma2 = float(np.sqrt(max(evals[0], 1e-12)))
    return sigma2 / sigma1


def subcell_line_mask(edge: np.ndarray) -> np.ndarray:
    """4px 小セルごとに PCA 判定し, 線なら True のマスクを返す。"""
    h, w = edge.shape
    gh, gw = h // SUB, w // SUB
    mask = np.zeros((gh, gw), dtype=bool)
    # まとめて座標抽出(高速化)
    ys_all, xs_all = np.nonzero(edge > 128)
    pts_all = np.stack([xs_all, ys_all], axis=1).astype(np.float64)
    cells = (ys_all // SUB) * gw + (xs_all // SUB)
    order = np.argsort(cells)
    cells_s = cells[order]
    pts_s = pts_all[order]
    bounds = np.searchsorted(cells_s, np.arange(gh * gw + 1))
    for ci in range(gh * gw):
        s, e = bounds[ci], bounds[ci + 1]
        if e - s < SUB_MIN_PX:
            continue
        pts = pts_s[s:e]
        if np.ptp(pts[:, 0]) < 1.0 and np.ptp(pts[:, 1]) < 1.0:
            continue  # 点に近い → 線でない
        if pca_ratio(pts) < SUB_RATIO_TH:
            cy, cx = divmod(ci, gw)
            mask[cy, cx] = True
    return mask


def classify(edge: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ms-any マスク, ms-all マスク) を返す。値は 16px セル単位。"""
    h, w = edge.shape
    gh, gw = h // SUB, w // SUB
    sub = subcell_line_mask(edge)

    n16y, n16x = h // CELL, w // CELL
    rate16 = np.zeros((n16y, n16x))
    for iy in range(n16y):
        for ix in range(n16x):
            r = sub[iy * 4:(iy + 1) * 4, ix * 4:(ix + 1) * 4]
            rate16[iy, ix] = r.mean()
    line16 = rate16 > SUB_RATE_TH

    line32 = np.zeros((n16y, n16x), dtype=bool)
    for iy in range(n16y - 1):
        for ix in range(n16x - 1):
            ys, xs = np.nonzero(edge[iy * CELL:(iy + 2) * CELL, ix * CELL:(ix + 2) * CELL] > 128)
            if ys.size < BIG_MIN_PX:
                continue
            pts = np.stack([xs, ys], axis=1).astype(np.float64)
            if np.ptp(pts[:, 0]) < 1.0 and np.ptp(pts[:, 1]) < 1.0:
                continue
            if pca_ratio(pts) < BIG_RATIO_TH:
                line32[iy:iy + 2, ix:ix + 2] = True

    return line16 | line32, line16 & line32


def render(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    canvas = np.zeros((h, w), dtype=np.uint8)
    n16y, n16x = mask.shape
    for iy in range(n16y):
        for ix in range(n16x):
            y0, x0 = iy * CELL, ix * CELL
            if mask[iy, ix]:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = 255
            else:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = gray[y0:y0 + CELL, x0:x0 + CELL].mean()
    return canvas


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    n_out = 0
    n_montage = 0
    for p in paths:
        stem = p.stem
        gray = load_gray(p)
        h, w = gray.shape
        ep = EDGE_DIR / f"{stem}.jpg"
        if not ep.exists():
            ep = EDGE_DIR / p.name
        edge = cv2.imread(str(ep), cv2.IMREAD_GRAYSCALE)
        if edge is None:
            raise RuntimeError(f"failed to read edge: {ep}")
        if edge.shape != (h, w):
            edge = cv2.resize(edge, (w, h), interpolation=cv2.INTER_NEAREST)

        vis_map: dict[str, np.ndarray] = {}
        for name in ("ms-any", "ms-all"):
            mask_any, mask_all = classify(edge)
            mask = mask_any if name == "ms-any" else mask_all
            vis = render(gray, mask)
            outp = OUT_DIR / name
            outp.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(outp / f"{stem}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
            n_out += 1
            vis_map[name] = vis

        # モンタージュ: original + step3 pca-canny + ms-any + ms-all
        step3 = cv2.imread(str(STEP3_CANNY_DIR / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
        if step3 is None:
            raise RuntimeError(f"failed to read step3: {STEP3_CANNY_DIR / stem}")
        if step3.shape != (h, w):
            step3 = cv2.resize(step3, (w, h), interpolation=cv2.INTER_NEAREST)
        tiles = [
            ("original", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)),
            ("step3-canny", cv2.cvtColor(step3, cv2.COLOR_GRAY2BGR)),
            ("ms-any", cv2.cvtColor(vis_map["ms-any"], cv2.COLOR_GRAY2BGR)),
            ("ms-all", cv2.cvtColor(vis_map["ms-all"], cv2.COLOR_GRAY2BGR)),
        ]
        tile_h, tile_w = h, w
        label_h = 28
        montage = np.zeros((tile_h + label_h, (tile_w + 4) * len(tiles), 3), dtype=np.uint8)
        for i, (lab, t) in enumerate(tiles):
            x = i * (tile_w + 4)
            montage[label_h:label_h + tile_h, x:x + tile_w] = t
            cv2.putText(montage, lab, (x + 4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(MONTAGE_DIR / f"{stem}.jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
        n_montage += 1
    print(f"done: {n_out} rendered images, {n_montage} montages")


if __name__ == "__main__":
    main()
