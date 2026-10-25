import { defineConfig, loadEnv } from 'vite'

// GitHub Pages のリポジトリ名サブパスで配信するため base を固定する
// （architecture.md §7、D-007）
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const allowedHosts = env.ALLOWED_HOSTS
    ? env.ALLOWED_HOSTS.split(',').map((h) => h.trim())
    : [];
    
  return {
    server: { allowedHosts },
    base: '/BrowserMoji/',
  }
});
