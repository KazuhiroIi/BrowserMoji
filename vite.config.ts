import { defineConfig } from 'vite';

// GitHub Pages のリポジトリ名サブパスで配信するため base を固定する
// （architecture.md §7、D-007）
export default defineConfig({
  base: '/BrowserMoji/',
});
