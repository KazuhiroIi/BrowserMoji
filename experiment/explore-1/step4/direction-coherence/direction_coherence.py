"""Step4 案C: direction-coherence — 方向一貫性フィルタ(方向拡散)。

1. step3 と同じ PCA 判定で各セルの主軸方向 θ(0〜π)と線らしさ(σ2/σ1)を計算。
2. 8近傍で双方が線らしく主軸方向差が ANGLE_TH(=30度, 周期性考慮)以内なら接続。
3. 連結成分を取り、セル数 >= N のチェーンだけをエッジマス化(chain-4 / chain-8)。
4. 可視化: エッジマス=白セル、フィラー=セル平均輝度。JPEG q90。

出力:
  step4/direction-coherence/out/{chain-4|chain-8}/{stem}.jpg
  step4/direction-coherence/montage/{stem}.jpg  (original + pca-canny + chain-4 + chain-8)
"""

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
EXPL = ROOT.parent.parent
DATA_DIR = EXPL.parent.parent / "data"
EDGE_DIR = EXPL / "step2" / "canny-improved" / "out" / "bilateral-low50-clean"
STEP3_DIR = EXPL / "step3" / "pca-shape" / "out" / "canny-low50"
OUT_DIR = ROOT / "out"
MONTAGE_DIR = ROOT / "montage"

MAX_SIDE = 1280
CELL = 16
MIN_EDGE_PX = 15
LINE_RATIO_TH = 0.25
ANGLE_TH = np.deg2rad(30.0)
CHAIN_MIN = {"chain-4": 4, "chain-8": 8}


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read: {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def cell_stats(edge: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """各セルの (is_line, theta) を返す。theta は 0〜π, 非線セルは 0。"""
    h, w = edge.shape
    ny, nx = h // CELL, w // CELL
    is_line = np.zeros((ny, nx), dtype=bool)
    theta = np.zeros((ny, nx), dtype=np.float64)
    for cy in range(ny):
        for cx in range(nx):
            cell = edge[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL]
            ys, xs = np.nonzero(cell > 128)
            if ys.size < MIN_EDGE_PX:
                continue
            pts = np.stack([xs, ys], axis=1).astype(np.float64)
            pts -= pts.mean(axis=0)
            cov = pts.T @ pts / pts.shape[0]
            evals, evecs = np.linalg.eigh(cov)  # ascending
            s1 = float(np.sqrt(max(evals[1], 1e-12)))
            s2 = float(np.sqrt(max(evals[0], 1e-12)))
            if (s2 / s1) >= LINE_RATIO_TH:
                continue
            is_line[cy, cx] = True
            v = evecs[:, 1]  # 主軸
            theta[cy, cx] = np.arctan2(v[1], v[0]) % np.pi
    return is_line, theta


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % np.pi
    return min(d, np.pi - d)


def connected_components(is_line: np.ndarray, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """8近傍で方向一貫性のある接続を張り、連結成分ラベルとサイズを返す。-1 は未割当。"""
    n, m = is_line.shape
    label = np.full((n, m), -1, dtype=np.int32)
    sizes: list[int] = []
    for sy in range(n):
        for sx in range(m):
            if not is_line[sy, sx] or label[sy, sx] != -1:
                continue
            cid = len(sizes)
            stack = [(sy, sx)]
            label[sy, sx] = cid
            cnt = 0
            while stack:
                y, x = stack.pop()
                cnt += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        yy, xx = y + dy, x + dx
                        if not (0 <= yy < n and 0 <= xx < m):
                            continue
                        if label[yy, xx] != -1 or not is_line[yy, xx]:
                            continue
                        if angle_diff(theta[y, x], theta[yy, xx]) > ANGLE_TH:
                            continue
                        label[yy, xx] = cid
                        stack.append((yy, xx))
            sizes.append(cnt)
    return label, np.array(sizes, dtype=np.int32)


def render(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    canvas = np.zeros((h, w), dtype=np.uint8)
    for cy in range(0, h - CELL + 1, CELL):
        for cx in range(0, w - CELL + 1, CELL):
            if mask[cy // CELL, cx // CELL]:
                canvas[cy:cy + CELL, cx:cx + CELL] = 255
            else:
                canvas[cy:cy + CELL, cx:cx + CELL] = gray[cy:cy + CELL, cx:cx + CELL].mean()
    return canvas


def main() -> None:
    paths = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".png"})
    n_out = 0
    for p in paths:
        stem = p.stem
        gray = load_gray(p)
        h, w = gray.shape
        ep = EDGE_DIR / (stem + ".jpg")
        if not ep.exists():
            ep = EDGE_DIR / p.name
        edge = cv2.imread(str(ep), cv2.IMREAD_GRAYSCALE)
        if edge is None:
            raise RuntimeError(f"failed to read edge: {ep}")
        if edge.shape != (h, w):
            edge = cv2.resize(edge, (w, h), interpolation=cv2.INTER_NEAREST)

        is_line, theta = cell_stats(edge)
        label, sizes = connected_components(is_line, theta)
        sizes_padded = np.concatenate([sizes, [0]])  # label=-1 用の pad

        tiles = [cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)]
        labels = ["original"]
        sp = STEP3_DIR / f"{stem}.jpg"
        if sp.exists():
            t3 = cv2.imread(str(sp), cv2.IMREAD_COLOR)
            if t3 is not None:
                tiles.append(t3)
                labels.append("pca-canny")
        for name, nmin in CHAIN_MIN.items():
            mask = (label >= 0) & (sizes_padded[np.clip(label, 0, None)] >= nmin)
            vis = render(gray, mask)
            outp = OUT_DIR / name
            outp.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(outp / f"{stem}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
            n_out += 1
            tiles.append(cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR))
            labels.append(name)

        tile_h, tile_w = tiles[0].shape[:2]
        tiles = [cv2.resize(t, (tile_w, tile_h)) if t.shape[:2] != (tile_h, tile_w) else t for t in tiles]
        label_h = 28
        montage = np.zeros((tile_h + label_h, (tile_w + 4) * len(tiles), 3), dtype=np.uint8)
        for i, (t, lab) in enumerate(zip(tiles, labels)):
            x = i * (tile_w + 4)
            montage[label_h:label_h + tile_h, x:x + tile_w] = t
            cv2.putText(montage, lab, (x + 4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(MONTAGE_DIR / f"{stem}.jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"done: {n_out} rendered images, {len(paths)} montages")


if __name__ == "__main__":
    main()
