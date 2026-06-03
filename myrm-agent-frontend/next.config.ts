// next.config.ts
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import createNextIntlPlugin from 'next-intl/plugin';
import type { NextConfig } from 'next';
import withSerwistInit from '@serwist/next';
import type { withSentryConfig as sentryConfigWrapper } from '@sentry/nextjs';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

// 检测构建模式：tauri 或 sandbox
// 注意：Tauri 模式现在也使用 standalone，以支持动态路由和 API 路由
const isTauriBuild = process.env.BUILD_MODE === 'tauri';

// Serwist PWA Configuration
const withSerwist = withSerwistInit({
  swSrc: 'src/app/sw.ts',
  swDest: 'public/sw.js',
  disable: isTauriBuild || process.env.NODE_ENV === 'development',
  reloadOnOnline: false,
});

// Bundle Analyzer (optional, controlled by env var)
const ANALYZE = process.env.ANALYZE === 'true';
let withBundleAnalyzer: ((config: NextConfig) => NextConfig) | null = null;

if (ANALYZE) {
  try {
    withBundleAnalyzer = require('@next/bundle-analyzer')({
      enabled: true,
    });
    console.log('[Build] Bundle analyzer enabled');
  } catch {
    console.warn('[Build] Bundle analyzer enabled but @next/bundle-analyzer not installed.');
  }
}

// Sentry integration (optional, controlled by env var)
const SENTRY_ENABLED = process.env.NEXT_PUBLIC_SENTRY_ENABLED === 'true';
let withSentryConfig: typeof sentryConfigWrapper | null = null;

if (SENTRY_ENABLED) {
  try {
    const { withSentryConfig: _withSentryConfig } = require('@sentry/nextjs') as typeof import('@sentry/nextjs');
    withSentryConfig = _withSentryConfig;
    console.log('[Build] Sentry integration enabled');
  } catch {
    console.warn('[Build] Sentry enabled but @sentry/nextjs not installed. Install with: bun add @sentry/nextjs');
  }
}

// 检测构建模式：tauri 或 sandbox
// 注意：Tauri 模式现在也使用 standalone，以支持动态路由和 API 路由
// (isTauriBuild is defined above for Serwist)

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: {
    root: frontendRoot,
    resolveAlias: {
      '#locales': path.join(frontendRoot, 'locales'),
    },
  },

  // 避免 Next.js 对 API 代理路径进行 308 trailing slash redirect
  skipTrailingSlashRedirect: true,

  // 所有模式都使用 standalone，在 Tauri 内运行完整的 Next.js 服务器
  output: 'standalone',
  
  // 生产构建由独立类型检查流程把关，避免 Next 构建阶段重复阻塞。
  typescript: {
    ignoreBuildErrors: true,
  },
  
  images: {
    // Tauri 模式禁用图片优化（本地运行无需优化）
    unoptimized: isTauriBuild,
    remotePatterns: [
      {
        hostname: 's2.googleusercontent.com',
      },
      {
        hostname: 'lh3.googleusercontent.com',
      },
      {
        hostname: '*.googleusercontent.com',
      },
      {
        hostname: 'localhost',
      },
      {
        hostname: '127.0.0.1',
      },
    ],
  },
  
  // 仅在生产环境启用严格模式，避免开发模式的双重渲染消耗资源
  reactStrictMode: process.env.NODE_ENV === 'production',
  
  allowedDevOrigins: ['127.0.0.1', 'localhost'],

  // Disable dev indicators to prevent overlay interference with UI interactions
  devIndicators: false,
  
  // 优化Turbopack性能
  experimental: {
    // 减少并行编译任务，降低CPU占用
    cpus: 4,
  },
  
  // Webpack优化配置（当使用Webpack时生效）
  webpack: (config, { isServer }) => {
    if (!isServer) {
      // 分包策略优化
      config.optimization = {
        ...config.optimization,
        splitChunks: {
          chunks: 'all',
          cacheGroups: {
            // React核心库单独分包
            react: {
              test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/,
              name: 'react-vendor',
              priority: 40,
              reuseExistingChunk: true,
            },
            // Next.js核心库
            nextjs: {
              test: /[\\/]node_modules[\\/]next[\\/]/,
              name: 'nextjs-vendor',
              priority: 35,
              reuseExistingChunk: true,
            },
            // UI库单独分包
            ui: {
              test: /[\\/]node_modules[\\/](@radix-ui|lucide-react|cmdk)[\\/]/,
              name: 'ui-vendor',
              priority: 30,
              reuseExistingChunk: true,
            },
            // 其他大型库
            libs: {
              test: /[\\/]node_modules[\\/]/,
              name: 'libs-vendor',
              priority: 20,
              minSize: 100000,
              reuseExistingChunk: true,
            },
            // 公共代码
            common: {
              minChunks: 2,
              priority: 10,
              reuseExistingChunk: true,
            },
          },
        },
      };
    }
    return config;
  },
  
  // API proxy: forward /api/v1/* to the Python FastAPI backend.
  // API_HOST defaults to localhost; set to Docker service name (e.g. "backend") for container builds.
  async redirects() {
    return [
      { source: '/auth/register', destination: '/auth/login', permanent: false },
      { source: '/auth/verify-email', destination: '/auth/login', permanent: false },
      { source: '/chat', destination: '/', permanent: false },
    ];
  },

  async rewrites() {
    const apiHost = process.env.API_HOST || '127.0.0.1';
    // Default matches `uv run run.py` (PORT=8080). WebUI mode (`run.py --webui`) uses 25808 — set API_PORT in .env.local.
    const apiPort = process.env.API_PORT || '8080';
    return [
      {
        source: '/api/v1/:path*',
        destination: `http://${apiHost}:${apiPort}/api/v1/:path*`,
      },
      {
        source: '/webui/:path*',
        destination: `http://${apiHost}:${apiPort}/webui/:path*`,
      },
    ];
  },

  // Enable Cross-Origin Isolation for advanced features (SharedArrayBuffer support)
  // Using 'credentialless' instead of 'require-corp' to allow loading external CDN resources
  // in HTML artifact previews while still maintaining cross-origin isolation
  // 注意：Tauri 静态导出模式不支持 headers()
  ...(!isTauriBuild && {
    async headers() {
      return [
        {
          // Apply to all routes
          source: '/:path*',
          headers: [
            {
              key: 'Cross-Origin-Opener-Policy',
              value: 'same-origin',
            },
            {
              key: 'Cross-Origin-Embedder-Policy',
              value: 'credentialless',
            },
          ],
        },
      ];
    },
  }),
};

// Apply config wrappers in order
let finalConfig = withNextIntl(nextConfig);

// Apply Serwist PWA wrapper
finalConfig = withSerwist(finalConfig);

if (SENTRY_ENABLED && withSentryConfig) {
  finalConfig = withSentryConfig(finalConfig, {
    // Sentry webpack plugin options
    silent: true, // Suppress logs during build
    hideSourceMaps: true, // Hide source maps from generated client bundles
    disableLogger: true, // Disable Sentry logger in production builds
  });
}

if (ANALYZE && withBundleAnalyzer) {
  finalConfig = withBundleAnalyzer(finalConfig);
}

export default finalConfig;
