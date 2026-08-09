import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  assetsInclude: ['**/*.svg'],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    testTimeout: 30000,
    exclude: ['**/node_modules/**', '**/dist/**'],
    server: {
      deps: {
        // zod v4 的 ESM 入口以 `export { z }` 命名空间再导出，在 bun 运行时下
        // Vite SSR transform 会丢失该绑定（zod#6018 / vitest#10359 / oven-sh/bun#21614）。
        // inline 让 vitest 走 vite 解析编译后的入口，与生产构建一致。
        inline: ['zod'],
      },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/__tests__/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData',
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@shared': path.resolve(__dirname, '../shared'),
      '#locales': path.resolve(__dirname, './locales'),
    },
  },
});
