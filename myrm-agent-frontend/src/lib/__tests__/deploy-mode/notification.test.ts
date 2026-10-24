/**
 * Notification stream URL resolution.
 *
 * Covers the desktop/loopback rule: the notification SSE must stay same-origin so the browser does not
 * block it as cross-origin (the backend sends credentials but no Access-Control-Allow-Origin).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getNotificationStreamUrl } from '@/lib/deploy-mode';

const ENV_KEYS = ['NEXT_PUBLIC_DEPLOY_MODE', 'NEXT_PUBLIC_API_BASE_URL', 'NEXT_PUBLIC_BACKEND_BASE_URL'] as const;

function snapshotEnv(): Record<string, string | undefined> {
  return Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
}

function restoreEnv(snapshot: Record<string, string | undefined>): void {
  for (const key of ENV_KEYS) {
    const value = snapshot[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

function setHostname(hostname: string): void {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, hostname },
  });
}

describe('getNotificationStreamUrl', () => {
  const originalEnv = snapshotEnv();
  const originalLocation = window.location;

  afterEach(() => {
    restoreEnv(originalEnv);
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    delete (window as unknown as Record<string, unknown>).__TAURI__;
    delete (window as unknown as Record<string, unknown>).__MYRM_E2E_API_BASE__;
    delete (window as unknown as Record<string, unknown>).__MYRM_E2E_RUNTIME__;
    vi.unstubAllGlobals();
  });

  it('keeps the Tauri webview same-origin even when a backend base is configured', () => {
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'http://127.0.0.1:8080';
    (window as unknown as Record<string, unknown>).__TAURI__ = {};

    expect(getNotificationStreamUrl()).toBe('/api/v1/notifications/stream');
  });

  it('keeps a loopback WebUI same-origin', () => {
    setHostname('127.0.0.1');
    delete process.env.NEXT_PUBLIC_DEPLOY_MODE;

    expect(getNotificationStreamUrl()).toBe('/api/v1/notifications/stream');
  });

  it('uses the configured backend for a remote (non-loopback) host', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'https://backend.example.com';
    setHostname('cp.example.com');

    expect(getNotificationStreamUrl()).toBe('https://backend.example.com/api/v1/notifications/stream');
  });

  it('honours the E2E isolated API base', () => {
    (window as unknown as Record<string, unknown>).__MYRM_E2E_API_BASE__ = 'http://127.0.0.1:18080';

    expect(getNotificationStreamUrl()).toBe('http://127.0.0.1:18080/api/v1/notifications/stream');
  });
});
