import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { GlobalErrorBoundary } from '../GlobalErrorBoundary';

const CHUNK_RELOAD_KEY = 'myrm-chunk-reload-ts';

function ThrowError({ error }: { error: Error }): React.ReactNode {
  throw error;
}

function makeChunkLoadError(variant: string): Error {
  const errorMap: Record<string, () => Error> = {
    webpack: () => {
      const e = new Error('Loading chunk 123 failed');
      e.name = 'ChunkLoadError';
      return e;
    },
    vite: () => new Error('Failed to fetch dynamically imported module /assets/foo.js'),
    firefox: () => new Error('Importing a module script failed'),
    webpackMsg: () => new Error('Loading chunk abc123 failed'),
    generic: () => new Error('loading some chunk xyz failed'),
  };
  return (errorMap[variant] ?? errorMap.webpack)();
}

describe('GlobalErrorBoundary', () => {
  const originalLocation = window.location;
  const reloadMock = vi.fn();

  beforeEach(() => {
    sessionStorage.clear();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    Object.defineProperty(window, 'location', {
      value: { ...originalLocation, reload: reloadMock },
      writable: true,
    });
  });

  afterEach(() => {
    reloadMock.mockClear();
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    });
  });

  it('renders children when no error', () => {
    render(
      <GlobalErrorBoundary>
        <div data-testid="child">OK</div>
      </GlobalErrorBoundary>,
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('shows error page for generic errors', () => {
    render(
      <GlobalErrorBoundary>
        <ThrowError error={new Error('Some bug')} />
      </GlobalErrorBoundary>,
    );
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it('auto-reloads on ChunkLoadError (first attempt)', () => {
    render(
      <GlobalErrorBoundary>
        <ThrowError error={makeChunkLoadError('webpack')} />
      </GlobalErrorBoundary>,
    );
    expect(reloadMock).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(CHUNK_RELOAD_KEY)).toBeTruthy();
  });

  it('shows update page when reload already attempted within 5min', () => {
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));

    render(
      <GlobalErrorBoundary>
        <ThrowError error={makeChunkLoadError('webpack')} />
      </GlobalErrorBoundary>,
    );
    expect(reloadMock).not.toHaveBeenCalled();
    expect(screen.getByText(/App Updated/i)).toBeInTheDocument();
    expect(sessionStorage.getItem(CHUNK_RELOAD_KEY)).toBeNull();
  });

  it('auto-reloads when previous reload timestamp expired (>5min)', () => {
    const expired = Date.now() - 6 * 60 * 1000;
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(expired));

    render(
      <GlobalErrorBoundary>
        <ThrowError error={makeChunkLoadError('webpack')} />
      </GlobalErrorBoundary>,
    );
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  describe('isChunkLoadError detection', () => {
    const variants = ['webpack', 'vite', 'firefox', 'webpackMsg', 'generic'] as const;

    variants.forEach((variant) => {
      it(`detects ${variant} chunk error and triggers reload`, () => {
        reloadMock.mockClear();
        sessionStorage.clear();

        render(
          <GlobalErrorBoundary>
            <ThrowError error={makeChunkLoadError(variant)} />
          </GlobalErrorBoundary>,
        );
        expect(reloadMock).toHaveBeenCalledTimes(1);
      });
    });
  });

  it('refresh button reloads page on error page', () => {
    render(
      <GlobalErrorBoundary>
        <ThrowError error={new Error('Some bug')} />
      </GlobalErrorBoundary>,
    );
    const btn = screen.getByRole('button', { name: /Refresh Page/i });
    fireEvent.click(btn);
    expect(reloadMock).toHaveBeenCalled();
  });

  it('shows dev details in development mode', () => {
    vi.stubEnv('NODE_ENV', 'development');

    render(
      <GlobalErrorBoundary>
        <ThrowError error={new Error('dev error details')} />
      </GlobalErrorBoundary>,
    );
    expect(screen.getByText('Error details (dev mode)')).toBeInTheDocument();

    vi.unstubAllEnvs();
  });

  it('displays Chinese text when navigator.language starts with zh', () => {
    const langGetter = vi.spyOn(navigator, 'language', 'get');
    langGetter.mockReturnValue('zh-CN');

    render(
      <GlobalErrorBoundary>
        <ThrowError error={new Error('bug')} />
      </GlobalErrorBoundary>,
    );
    expect(screen.getByText('应用出错了')).toBeInTheDocument();

    langGetter.mockRestore();
  });

  it('displays English text when navigator.language is non-zh', () => {
    const langGetter = vi.spyOn(navigator, 'language', 'get');
    langGetter.mockReturnValue('en-US');

    render(
      <GlobalErrorBoundary>
        <ThrowError error={new Error('bug')} />
      </GlobalErrorBoundary>,
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    langGetter.mockRestore();
  });
});
