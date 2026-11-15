# -*- coding: utf-8 -*-
"""step5: unified pipeline + parameter comparison.

Stage1 detection (2 systems):
  canny-path:
    det-16px: cell edge px(>128) >= 15 and PCA sigma2/sigma1 < 0.25
    det-ms:   4px sub-cell PCA (sigma2/sigma1 < 0.4) -> 16px cell line-rate >= 25%
  edl-path: EDPF + straightness filter
    (bilateral d=7 sigma30/7 pre-stage, GradientThreshold=32,
     discard perp_var/par_var > 0.5, MIN_SEG_POINTS=15), rasterized to cells.
Stage2 direction-coherence chain (canny-path only):
  theta from cell PCA, 8-neighbor connect with angle diff <= th, chain length >= 3
Stage3 clean (all paths):
  white-cell connected components < 5 cells -> filler

Variants (7):
  A1 = det-16px + clean
  A2 = det-ms   + clean
  B1 = det-16px -> chain 30deg -> clean
  B2 = det-16px -> chain 45deg -> clean
  B3 = det-ms   -> chain 45deg -> clean
  C1 = edl      + clean
  C2 = edl      -> chain 45deg -> clean

Output:
  step5/unified/out/{variant}/{stem}.jpg   (edge cells = white, filler = cell mean gray, q90)
  step5/unified/montage/{stem}.jpg         (original + 7 variants, 4 cols x 2 rows)
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
EXPL = ROOT.parent.parent
DATA_DIR = EXPL.parent.parent / "data"
EDGE_DIR = EXPL / "step2" / "canny-improved" / "out" / "bilateral-low50-clean"
OUT_DIR = ROOT / "out"
MONTAGE_DIR = ROOT / "montage"

MAX_SIDE = 1280
CELL = 16
SUB = 4
MIN_EDGE_PX = 15       # det-16px minimum edge pixels
LINE_RATIO_TH = 0.25   # det-16px PCA ratio threshold
SUB_RATIO_TH = 0.4     # 4px sub-cell PCA ratio threshold
SUB_MIN_PX = 3
MS_RATE_TH = 0.25      # 16px cell sub-cell line rate threshold (effective from ms-any-lo25-ref)
CHAIN_MIN = 3          # minimum chain length
CLEAN_MIN = 5          # white-cell connected components smaller than this -> filler
ANGLE_THS = {"30": np.deg2rad(30.0), "45": np.deg2rad(45.0)}
ED_GRAD = 32           # EdgeDrawing GradientThresholdValue
ED_ANCHOR = 8
MIN_SEG_POINTS = 15
STRAIGHT_MAX_RATIO = 0.5  # perp_var / par_var above this => discard

VARIANTS = ["A1", "A2", "B1", "B2", "B3", "C1", "C2"]


def load_gray(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)  # Windows-safe (non-ASCII paths)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def load_edge(stem: str, name: str) -> np.ndarray:
    ep = EDGE_DIR / f"{stem}.jpg"
    if not ep.exists():
        ep = EDGE_DIR / f"{stem}.png"
    edge = cv2.imread(str(ep), cv2.IMREAD_GRAYSCALE)
    if edge is None:
        raise RuntimeError(f"failed to read edge: {ep}")
    return edge


def pca_of(pts: np.ndarray) -> tuple[float, np.ndarray]:
    """Return (sigma2/sigma1, principal axis unit vector)."""
    c = pts - pts.mean(axis=0)
    cov = c.T @ c / pts.shape[0]
    evals, evecs = np.linalg.eigh(cov)  # ascending
    s1 = float(np.sqrt(max(evals[1], 1e-12)))
    s2 = float(np.sqrt(max(evals[0], 1e-12)))
    return s2 / s1, evecs[:, 1]


def subcell_line_mask(edge: np.ndarray) -> np.ndarray:
    """4px sub-cell PCA line mask."""
    h, w = edge.shape
    gh, gw = h // SUB, w // SUB
    mask = np.zeros((gh, gw), dtype=bool)
    ys_all, xs_all = np.nonzero(edge > 128)
    if ys_all.size == 0:
        return mask
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
            continue
        if pca_of(pts)[0] < SUB_RATIO_TH:
            cy, cx = divmod(ci, gw)
            mask[cy, cx] = True
    return mask


def cell_stats(edge: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per 16px cell: (count, ratio, theta). theta in [0, pi), NaN when undefined."""
    h, w = edge.shape
    ny, nx = h // CELL, w // CELL
    count = np.zeros((ny, nx), dtype=np.int32)
    ratio = np.full((ny, nx), np.nan)
    theta = np.full((ny, nx), np.nan)
    ys_all, xs_all = np.nonzero(edge > 128)
    if ys_all.size == 0:
        return count, ratio, theta
    pts_all = np.stack([xs_all, ys_all], axis=1).astype(np.float64)
    cells = (ys_all // CELL) * nx + (xs_all // CELL)
    order = np.argsort(cells)
    cells_s = cells[order]
    pts_s = pts_all[order]
    bounds = np.searchsorted(cells_s, np.arange(ny * nx + 1))
    for ci in range(ny * nx):
        s, e = bounds[ci], bounds[ci + 1]
        if e - s < MIN_EDGE_PX:
            continue
        pts = pts_s[s:e]
        r, v = pca_of(pts)
        cy, cx = divmod(ci, nx)
        count[cy, cx] = e - s
        ratio[cy, cx] = r
        theta[cy, cx] = np.arctan2(v[1], v[0]) % np.pi
    return count, ratio, theta


def det_16px(edge: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(mask, theta) for det-16px."""
    count, ratio, theta = cell_stats(edge)
    mask = (count >= MIN_EDGE_PX) & (ratio < LINE_RATIO_TH)
    return mask, theta


def det_ms(edge: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(mask, theta) for det-ms. theta borrowed from cell PCA when available."""
    h, w = edge.shape
    sub = subcell_line_mask(edge)
    ny, nx = h // CELL, w // CELL
    mask = np.zeros((ny, nx), dtype=bool)
    for iy in range(ny):
        for ix in range(nx):
            if sub[iy * 4:(iy + 1) * 4, ix * 4:(ix + 1) * 4].mean() >= MS_RATE_TH:
                mask[iy, ix] = True
    _, _, theta = cell_stats(edge)
    return mask, theta


def angle_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = np.abs(a - b) % np.pi
    return np.minimum(d, np.pi - d)


def chain(mask: np.ndarray, theta: np.ndarray, angle_th: float) -> np.ndarray:
    """Direction-coherent connected components; keep chains >= CHAIN_MIN cells."""
    n, m = mask.shape
    label = np.full((n, m), -1, dtype=np.int32)
    sizes: list[int] = []
    for sy in range(n):
        for sx in range(m):
            if not mask[sy, sx] or label[sy, sx] != -1:
                continue
            cid = len(sizes)
            stack = [(sy, sx)]
            label[sy, sx] = cid
            cnt = 0
            while stack:
                y, x = stack.pop()
                cnt += 1
                ty = theta[y, x]
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        yy, xx = y + dy, x + dx
                        if not (0 <= yy < n and 0 <= xx < m):
                            continue
                        if label[yy, xx] != -1 or not mask[yy, xx]:
                            continue
                        if np.isnan(ty) or np.isnan(theta[yy, xx]):
                            continue
                        if angle_diff(ty, theta[yy, xx]) > angle_th:
                            continue
                        label[yy, xx] = cid
                        stack.append((yy, xx))
            sizes.append(cnt)
    if not sizes:
        return np.zeros_like(mask)
    sizes_a = np.array(sizes, dtype=np.int32)
    return (label >= 0) & (sizes_a[np.clip(label, 0, None)] >= CHAIN_MIN)


def edl_segments(gray: np.ndarray) -> list:
    """EDPF segments with straightness filter."""
    src = cv2.bilateralFilter(gray, d=7, sigmaColor=30, sigmaSpace=7)
    ed = cv2.ximgproc.createEdgeDrawing()
    params = ed.Params()
    params.GradientThresholdValue = ED_GRAD
    params.AnchorThresholdValue = ED_ANCHOR
    ed.setParams(params)
    ed.detectEdges(src)
    segs = ed.getSegments()
    out = []
    for s in segs:
        if len(s) < MIN_SEG_POINTS:
            continue
        pts = np.asarray(s, dtype=np.float64)  # (x, y)
        if len(pts) >= 3:
            c = pts - pts.mean(axis=0)
            cov = c.T @ c / len(c)
            vals, _ = np.linalg.eigh(cov)
            par_var, perp_var = vals[1], vals[0]
            if par_var > 0 and perp_var / par_var > STRAIGHT_MAX_RATIO:
                continue
        out.append(pts)
    return out


def edl_cells(gray: np.ndarray, segs: list) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize segments to a cell mask; theta per cell from segment directions."""
    h, w = gray.shape
    gh, gw = (h + CELL - 1) // CELL, (w + CELL - 1) // CELL
    mask = np.zeros((gh, gw), dtype=bool)
    theta = np.full((gh, gw), np.nan)
    vx = np.zeros((gh, gw))
    vy = np.zeros((gh, gw))
    pts_list = [np.rint(s / CELL).astype(np.int32) for s in segs]
    cv2.polylines(mask, pts_list, isClosed=False, color=1, thickness=1, lineType=cv2.LINE_8)
    for pts in segs:
        n = len(pts)
        if n >= 2:
            c = pts - pts.mean(axis=0)
            cov = c.T @ c / n
            evals, evecs = np.linalg.eigh(cov)
            v = evecs[:, 1]
            if evals[1] > 0:
                cells = np.rint(pts / CELL).astype(np.int32)
                cy, cx = cells[:, 1], cells[:, 0]
                ok = (cy >= 0) & (cy < gh) & (cx >= 0) & (cx < gw)
                vx[cy[ok], cx[ok]] += v[0]
                vy[cy[ok], cx[ok]] += v[1]
    has = (vx != 0) | (vy != 0)
    theta[has] = np.arctan2(vy[has], vx[has]) % np.pi
    return mask, theta


def clean(mask: np.ndarray) -> np.ndarray:
    """Isolated edge-cell removal: white-cell components < CLEAN_MIN -> filler."""
    m = mask.astype(np.uint8)
    n, labels = cv2.connectedComponents(m, connectivity=8)
    out = mask.copy()
    for cid in range(1, n):
        if np.count_nonzero(labels == cid) < CLEAN_MIN:
            out[labels == cid] = False
    return out


def render(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    canvas = np.zeros((h, w), dtype=np.uint8)
    ny, nx = mask.shape
    for iy in range(ny):
        for ix in range(nx):
            y0, x0 = iy * CELL, ix * CELL
            if mask[iy, ix]:
                canvas[y0:y0 + CELL, x0:x0 + CELL] = 255
            else:
                y1, x1 = min(y0 + CELL, h), min(x0 + CELL, w)
                canvas[y0:y1, x0:x1] = gray[y0:y1, x0:x1].mean()
    return canvas


def write_jpg(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError(f"encode failed: {path}")
    buf.tofile(str(path))


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    outdirs = {v: OUT_DIR / v for v in VARIANTS}
    n_out = 0
    for p in paths:
        stem = p.stem
        gray = load_gray(p)
        h, w = gray.shape
        edge = load_edge(stem, p.name)
        if edge.shape != (h, w):
            edge = cv2.resize(edge, (w, h), interpolation=cv2.INTER_NEAREST)

        m16, t16 = det_16px(edge)
        mms, tms = det_ms(edge)
        segs = edl_segments(gray)
        medl, tedl = edl_cells(gray, segs)

        results: dict[str, np.ndarray] = {
            "A1": clean(m16),
            "A2": clean(mms),
            "B1": clean(chain(m16, t16, ANGLE_THS["30"])),
            "B2": clean(chain(m16, t16, ANGLE_THS["45"])),
            "B3": clean(chain(mms, tms, ANGLE_THS["45"])),
            "C1": clean(medl),
            "C2": clean(chain(medl, tedl, ANGLE_THS["45"])),
        }
        for v in VARIANTS:
            vis = render(gray, results[v])
            write_jpg(outdirs[v] / f"{stem}.jpg", vis)
            n_out += 1

        # montage: original + 7 variants, 4 cols x 2 rows
        tiles = [("original", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))]
        tiles += [(v, cv2.cvtColor(render(gray, results[v]), cv2.COLOR_GRAY2BGR)) for v in VARIANTS]
        th, tw = h, w
        gap, label_h, ncols = 4, 28, 4
        rows = 2
        montage = np.zeros((label_h + rows * th + (rows - 1) * gap, (tw + gap) * ncols, 3), dtype=np.uint8)
        for i, (lab, t) in enumerate(tiles):
            r, c = divmod(i, ncols)
            y = label_h + r * (th + gap)
            x = c * (tw + gap)
            montage[y:y + th, x:x + tw] = t
            cv2.putText(montage, lab, (x + 4, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        write_jpg(MONTAGE_DIR / f"{stem}.jpg", montage)
        print(f"{stem}: edl_segs={len(segs)} "
              + " ".join(f"{v}={int(results[v].sum())}" for v in VARIANTS))
    print(f"done: {n_out} rendered images, {len(paths)} montages")


if __name__ == "__main__":
    main()
