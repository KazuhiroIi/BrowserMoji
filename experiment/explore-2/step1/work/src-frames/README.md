# src-frames/ — sample.mp4 からのフレーム抽出(不使用)

当初、採点用画像に sample.mp4 の鮮明フレームを使う想定だった。

- `pick_frames.py` / `select_sharp.py`: 1秒毎に ffmpeg で抽出した23枚の候補
  (`candidates/`)から、ラプラシアン分散 (variance of Laplacian) による
  シャープネススコアで時間的に分散しながら上位10枚を選ぶスクリプト。
- 抽出したフレームはいずれもぼやけているため、採点用には**不使用**と判断した。
  選ばれた10枚は work 直下の `video_*.jpg` として保存していたが、削除済み。
