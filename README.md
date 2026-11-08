# BrowserMoji

スマートフォンのブラウザで、カメラ映像をリアルタイムに日本語全角文字のアスキーアートへ変換して表示する Web アプリです。映像の処理はすべて端末内で完結し、外部へ送信されません。

- 要件: [docs/requirements.md](docs/requirements.md)
- 設計: [docs/architecture.md](docs/architecture.md)
- 設計判断の記録: [docs/decisions/](docs/decisions/)

## 開発

```sh
npm install
npm run dev      # ローカル開発サーバー
npm run build    # 本番ビルド（base: /BrowserMoji/）
npm run preview  # ビルド結果のローカル確認
```

### テスト

実機での撮影テストを自動化する e2e テストがある。`data/sample.mp4`（実機で撮影した映像）をブラウザに入力し、アプリの起動から描画までを本番ビルドに対して確認する。

- `test:e2e`: 正しさの確認（黒画面・白画面・出力崩れの検出。合格 / 不合格で判定）
- `test:perf`: 性能計測（CPU スロットリング 1x / 4x / 20x で fps を記録し、前回実行との差分を表示。リグレッション検知に使う。GPU は実機と異なるため絶対値ではなく相対比較用）

詳細（準備・仕組み・既知の発見）は [e2e/README.md](e2e/README.md) を参照。

```sh
npx playwright install chromium  # 初回のみ
npm run test:media               # テスト用メディアの生成（ffmpeg が必要・初回のみ）
npm run test:e2e                 # 正しさの確認
npm run test:perf                # 性能計測（前回との差分表示）
```

配信は GitHub Pages（`https://kazuhiroii.github.io/BrowserMoji/`）を予定しています。

## ライセンス

[MIT License](LICENSE)
