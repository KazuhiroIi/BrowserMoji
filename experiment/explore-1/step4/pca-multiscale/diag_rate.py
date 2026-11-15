"""診断: 16px 小セル線率のしきい値感度確認(参考出力 rate>=0.25)。"""
from pathlib import Path
import cv2
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pca_multiscale import (EDGE_DIR, DATA_DIR, OUT_DIR, MAX_SIDE, load_gray,
                            subcell_line_mask, render, CELL)

LO = 0.25
out_lo = OUT_DIR / "ms-any-lo25-ref"
n = 0
for p in sorted(DATA_DIR.glob("*.jpg")) + sorted(DATA_DIR.glob("*.png")):
    stem = p.stem
    gray = load_gray(p)
    h, w = gray.shape
    ep = EDGE_DIR / f"{stem}.jpg"
    edge = cv2.imread(str(ep), cv2.IMREAD_GRAYSCALE)
    if edge is None:
        continue
    if edge.shape != (h, w):
        edge = cv2.resize(edge, (w, h), interpolation=cv2.INTER_NEAREST)
    sub = subcell_line_mask(edge)
    ny, nx = h // CELL, w // CELL
    rate = np.zeros((ny, nx))
    for iy in range(ny):
        for ix in range(nx):
            rate[iy, ix] = sub[iy*4:(iy+1)*4, ix*4:(ix+1)*4].mean()
    mask = rate >= LO
    vis = render(gray, mask)
    out_lo.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_lo / f"{stem}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
    s3 = cv2.imread(str(Path(__file__).resolve().parent.parent.parent / "step3" / "pca-shape" / "out" /
                        "canny-low50" / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
    s3n = int(np.count_nonzero(s3 == 255)) // 256
    a = cv2.imread(str(OUT_DIR / "ms-any" / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
    al = cv2.imread(str(OUT_DIR / "ms-all" / f"{stem}.jpg"), cv2.IMREAD_GRAYSCALE)
    an = int(np.count_nonzero(a == 255)) // 256
    aln = int(np.count_nonzero(al == 255)) // 256
    print(f"{stem}: step3={s3n} ms-any(50%)={an} ms-all={aln} ms-any-lo25={int(mask.sum())}")
    n += 1
print("done", n)
