"""candidates/ のフレームをラプラシアン分散でスコアリングし、時間的に分散しながら
シャープネス上位10枚を選んで work/ 直下に video_XX_tYY.YYs.jpg として保存する。
ffmpeg の fps=1 出力 (cand_00001.jpg = 約1秒毎) を前提とする。
"""
import cv2
from pathlib import Path

WORK = Path("candidates")
OUT = Path("..")
N_PICK = 10
DURATION = 23.41

samples = []
for p in sorted(WORK.glob("cand_*.jpg")):
    n = int(p.stem.split("_")[1])
    t = n / 1.0  # fps=1 で抽出
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    img = cv2.resize(img, (960, int(960 * img.shape[0] / img.shape[1])))
    sharp = cv2.Laplacian(img, cv2.CV_64F).var()
    samples.append((t, sharp, p))

samples.sort(key=lambda s: -s[1])
picked = []
min_gap = DURATION / (N_PICK + 1)
for t, s, p in samples:
    if all(abs(t - pt) >= min_gap for pt, _, _ in picked):
        picked.append((t, s, p))
    if len(picked) == N_PICK:
        break
if len(picked) < N_PICK:
    for t, s, p in samples:
        if (t, p) not in [(a, c) for a, _, c in picked] and all(abs(t - pt) >= 1.0 for pt, _, _ in picked):
            picked.append((t, s, p))
        if len(picked) == N_PICK:
            break

picked.sort()
for i, (t, s, p) in enumerate(picked, 1):
    dst = OUT / f"video_{i:02d}_t{t:05.1f}s.jpg"
    dst.write_bytes(p.read_bytes())
    print(f"{dst.name}  sharpness={s:.1f}")
