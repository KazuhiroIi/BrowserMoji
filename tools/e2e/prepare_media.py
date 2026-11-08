"""e2e テスト用メディアの生成（npm run test:media で実行）。

data/sample.mp4（120fps 撮影の実機映像）から、ブラウザテスト用の入力を作る:
- data/sample30.webm: 30fps に間引いたクリップ。実機カメラの実効 fps に近づけるため
  （Playwright 同梱の Chromium は H.264 を再生できないため VP9/WebM にエンコードする）
- data/test-frame.png: 固定フレームテストの入力元になる 1 フレーム
- data/still30.webm: test-frame.png から作った全フレーム同一の動画（lossless VP9）。
  正しさの pixel 比較の入力。canvas.captureStream() ではヘッドレスで
  requestVideoFrameCallback が発火しないため、動画方式に統一する

data/ は .gitignore 済みなので生成物はリポジトリに入らない。
ffmpeg が必要（PATH 上にあること）。
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SRC = DATA / "sample.mp4"
CLIP = DATA / "sample30.webm"
FRAME = DATA / "test-frame.png"
STILL = DATA / "still30.webm"

# 固定フレームの抽出位置（秒）。映像の中で構図が安定している範囲を選ぶ
FRAME_AT_SEC = 5
# still 動画の長さ（秒）。テスト 1 回分より長ければよい
STILL_DURATION = 20


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True)


def main() -> None:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg が見つかりません。PATH 上にインストールしてください。", file=sys.stderr)
        sys.exit(1)
    if not SRC.exists():
        print(f"{SRC} がありません。実機で撮影した sample.mp4 を配置してください。", file=sys.stderr)
        sys.exit(1)

    DATA.mkdir(parents=True, exist_ok=True)

    # 30fps へ間引いて VP9/WebM でエンコード。
    # -deadline realtime -cpu-used 8: 品質より生成速度優先（テスト入力としては十分）
    run_ffmpeg(
        [
            "-i", str(SRC),
            "-vf", "fps=30",
            "-c:v", "libvpx-vp9",
            "-deadline", "realtime",
            "-cpu-used", "8",
            "-crf", "32",
            "-b:v", "0",
            "-an",
            str(CLIP),
        ]
    )
    print(f"生成: {CLIP}")

    # 1 フレームの抽出（still 動画の入力元）
    run_ffmpeg(
        [
            "-ss", str(FRAME_AT_SEC),
            "-i", str(SRC),
            "-frames:v", "1",
            str(FRAME),
        ]
    )
    print(f"生成: {FRAME}")

    # 全フレーム同一の動画（lossless VP9）。decoded 後の全フレームが pixel 等価になる
    run_ffmpeg(
        [
            "-loop", "1",
            "-framerate", "30",
            "-i", str(FRAME),
            "-t", str(STILL_DURATION),
            "-c:v", "libvpx-vp9",
            "-lossless", "1",
            "-an",
            str(STILL),
        ]
    )
    print(f"生成: {STILL}")


if __name__ == "__main__":
    main()
