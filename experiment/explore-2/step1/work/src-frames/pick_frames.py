"""sample.mp4 から鮮明(ぼやけていない)フレームを10枚選んで保存する。

方法: 一定間隔でサンプルフレームを抽出し、各フレームのグレースケール画像に
対してラプラシアン分散(variance of Laplacian)を計算してシャープネスを測る。
時間的に分散するように(連続フレームに偏らないよう)スコア上位を間引いて選ぶ。
"""
import cv2
import numpy as np
from pathlib import Path

VIDEO = Path("../../data/sample.mp4")
OUT = Path(".")
WORK = Path("candidates")
N_PICK = 10
SAMPLE_FPS = 1.0  # 1秒ごとに候補を取る

WORK.mkdir(exist_ok=True)
samples = []  # (t_sec, sharpness, path)

cap = cv2.VideoCapture(str(VIDEO))
ok, frame = cap.read()
assert ok, "cannot read video"
height, width = frame.shape[:2]
avg_fps = 24345000 / 1053451  # ffprobe: 1920x1080 h264
total = int(23.41 * avg_fps)  # ffprobe duration
duration = 23.41
print(f"fps={avg_fps:.2f}, frames={total}, duration={duration:.1f}s")

t = 0.0
frame_idx = 0
next_t = 0.0
while True:
    if frame_idx >= next_t * avg_fps:
        small = cv2.resize(frame, (960, int(960 * frame.shape[0] / frame.shape[1])))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
        p = WORK / f"cand_{t:08.2f}.jpg"
        cv2.imwrite(str(p), frame)
        samples.append((t, sharp, p))
        next_t += 1.0 / SAMPLE_FPS
        if t >= duration - 0.5:
            break
    ok, frame = cap.read()
    if not ok:
        break
    frame_idx += 1
    t = frame_idx / avg_fps
cap.release()

# 時間的に離した選択: 貪欲に「最後の選択から min_gap 以上」を優先
samples.sort(key=lambda s: -s[1])
picked = []
min_gap = duration / (N_PICK + 1)
for t, s, p in samples:
    if all(abs(t - pt) >= min_gap for pt, _ in picked):
        picked.append((t, p))
    if len(picked) == N_PICK:
        break
# 足りなければ gap 緩和
if len(picked) < N_PICK:
    for t, s, p in samples:
        if (t, p) not in picked and all(abs(t - pt) >= 1.0 for pt, _ in picked):
            picked.append((t, p))
        if len(picked) == N_PICK:
            break

picked.sort()
for i, (t, p) in enumerate(picked, 1):
    dst = OUT / f"video_{i:02d}_t{t:07.2f}s.jpg"
    dst.write_bytes(p.read_bytes())
    print(f"{dst.name}  sharpness={[s for tt, s, pp in samples if pp == p][0]:.1f}")
