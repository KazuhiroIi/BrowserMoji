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

配信は GitHub Pages（`https://kazuhiroii.github.io/BrowserMoji/`）を予定しています。

## ライセンス

[MIT License](LICENSE)
