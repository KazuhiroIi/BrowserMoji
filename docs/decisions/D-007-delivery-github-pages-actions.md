# D-007: 配信は GitHub Pages + GitHub Actions

- 状態: 🔒（確定）
- 関連: N-6, E-3, architecture.md §7

## 背景

HTTPS での静的配信が必要（E-3, N-6）。カメラは secure context でしか使えないため、配信環境は HTTPS が必須。

## 選択肢

1. **GitHub Pages + GitHub Actions（public リポジトリ、main への push で deploy）**
2. 別の静的ホスティング（Netlify / Vercel 等）
3. GitHub Pages の legacy ブランチビルド（gh-pages ブランチ）

## 決定

- **GitHub Pages を GitHub Actions で配信する**（public リポジトリ、main への push で deploy）
- ワークフローは `.github/workflows/deploy.yml` に置く（build → upload-pages-artifact → deploy-pages）
- ビルドの base は `/BrowserMoji/`（リポジトリ名サブパス。architecture.md §7）

## 理由

- リポジトリが既に GitHub 上にあり、コードから配信までを同じ場所で完結できる
- public リポジトリの GitHub Pages + Actions は無料で使える
- legacy ブランチビルドはキャッシュ・反映の制御がActions より弱く、手順が不透明になりやすい
