import { defineConfig } from '@playwright/test';

/**
 * e2e テスト（e2e/README.md を参照）。
 * - 対象は本番ビルド（npm run build && npm run preview）。dev server は
 *   最適化前コードで数値が変わるため、性能計測は本番同等コードで行う
 * - 正しさの pixel 比較はヘッドレス（SwiftShader のソフトウェア描画）の方が
 *   環境差が少なく決定的なので、ヘッドレスのままにする
 * - テスト間で results/ の成果物を受け渡すため workers を 1 に固定する
 */
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: 'http://localhost:4173',
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  },
  webServer: {
    command: 'npm run build && npm run preview',
    url: 'http://localhost:4173/BrowserMoji/',
    reuseExistingServer: true,
    timeout: 120_000,
  },
  reporter: [['list']],
});
