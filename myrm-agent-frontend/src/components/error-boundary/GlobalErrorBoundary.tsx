'use client';

import React, { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  isChunkError: boolean;
}

const CHUNK_RELOAD_KEY = 'myrm-chunk-reload-ts';
const CHUNK_RELOAD_EXPIRY_MS = 5 * 60 * 1000;

function isChunkLoadError(error: Error): boolean {
  const msg = error.message || '';
  const name = error.name || '';
  return (
    name === 'ChunkLoadError' ||
    msg.includes('Loading chunk') ||
    msg.includes('Failed to fetch dynamically imported module') ||
    msg.includes('Importing a module script failed') ||
    /loading .+ chunk .+ failed/i.test(msg)
  );
}

const AlertIcon = () => (
  <svg
    width="32"
    height="32"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const RefreshIcon = ({ size = 32 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
    <path d="M21 21v-5h-5" />
  </svg>
);

function getLocaleTexts(): Record<string, string> {
  const lang = typeof navigator !== 'undefined' ? navigator.language : 'en';
  const isZh = lang.startsWith('zh');
  return isZh
    ? {
        title: '应用出错了',
        description: '抱歉，应用遇到了意外错误。我们已自动记录此问题。',
        devDetails: '错误详情（开发模式）',
        refresh: '刷新页面',
        contact: '如果问题持续，请联系技术支持',
        updateTitle: '应用已更新',
        updateDescription: '检测到版本更新，请刷新页面以加载最新内容。',
        updateRefresh: '刷新页面',
      }
    : {
        title: 'Something went wrong',
        description: 'An unexpected error occurred. It has been automatically logged.',
        devDetails: 'Error details (dev mode)',
        refresh: 'Refresh Page',
        contact: 'If the problem persists, please contact support',
        updateTitle: 'App Updated',
        updateDescription: 'A new version is available. Please refresh to load the latest content.',
        updateRefresh: 'Refresh Page',
      };
}

/**
 * Global Error Boundary
 *
 * - Catches all unhandled React rendering errors
 * - Auto-recovers from ChunkLoadError (stale chunks after deployment)
 *   with a single transparent reload + sessionStorage-based anti-loop guard
 * - Falls back to a user-friendly error page for other errors
 * - Zero external dependencies (no icon library) to stay resilient when chunks fail
 * - Browser-locale based i18n fallback (outside NextIntlClientProvider)
 */
export class GlobalErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, isChunkError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, isChunkError: isChunkLoadError(error) };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    if (isChunkLoadError(error)) {
      this.attemptChunkReload(error);
      return;
    }

    console.error('[GlobalErrorBoundary] Caught error:', error, errorInfo);
    this.logErrorToBackend(error, errorInfo);
  }

  private attemptChunkReload(error: Error) {
    if (typeof window === 'undefined') return;

    const lastReloadTs = sessionStorage.getItem(CHUNK_RELOAD_KEY);
    const now = Date.now();
    const canReload = !lastReloadTs || now - Number(lastReloadTs) > CHUNK_RELOAD_EXPIRY_MS;

    if (canReload) {
      console.warn('[GlobalErrorBoundary] ChunkLoadError detected, auto-reloading:', error.message);
      sessionStorage.setItem(CHUNK_RELOAD_KEY, String(now));
      window.location.reload();
      return;
    }

    console.warn('[GlobalErrorBoundary] ChunkLoadError persists after reload, showing update page');
    sessionStorage.removeItem(CHUNK_RELOAD_KEY);
  }

  private async logErrorToBackend(error: Error, errorInfo: React.ErrorInfo) {
    try {
      await fetch('/api/v1/logs/client-error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          error: error.toString(),
          stack: error.stack,
          componentStack: errorInfo.componentStack,
          userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
          url: typeof window !== 'undefined' ? window.location.href : 'unknown',
          timestamp: new Date().toISOString(),
        }),
      });
    } catch {
      // Silent fail: logging errors shouldn't block user experience
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, isChunkError: false });
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const t = getLocaleTexts();

    if (this.state.isChunkError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background p-4">
          <div className="w-full max-w-md space-y-6 rounded-lg border border-border bg-card p-6 shadow-lg">
            <div className="flex items-center gap-3 text-primary">
              <RefreshIcon />
              <h1 className="text-2xl font-bold">{t.updateTitle}</h1>
            </div>
            <p className="text-muted-foreground">{t.updateDescription}</p>
            <button
              onClick={this.handleReset}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {t.updateRefresh}
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md space-y-6 rounded-lg border border-destructive/50 bg-card p-6 shadow-lg">
          <div className="flex items-center gap-3 text-destructive">
            <AlertIcon />
            <h1 className="text-2xl font-bold">{t.title}</h1>
          </div>

          <div className="space-y-3">
            <p className="text-muted-foreground">{t.description}</p>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="rounded bg-muted p-3 text-sm">
                <summary className="cursor-pointer font-mono text-destructive">{t.devDetails}</summary>
                <pre className="mt-2 overflow-auto text-xs">
                  {this.state.error.toString()}
                  {'\n\n'}
                  {this.state.error.stack}
                </pre>
              </details>
            )}
          </div>

          <button
            onClick={this.handleReset}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <RefreshIcon size={16} />
            {t.refresh}
          </button>

          <p className="text-center text-sm text-muted-foreground">{t.contact}</p>
        </div>
      </div>
    );
  }
}
