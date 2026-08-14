import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockBackendBase = vi.hoisted(() => ({ value: '' }));

vi.mock('@/lib/api', () => ({
  BACKEND_BASE_URL: {
    toString: () => mockBackendBase.value,
    valueOf: () => mockBackendBase.value,
  } as unknown as string,
  getApiUrl: vi.fn(),
}));

import { buildPublicArtifactShareUrl } from '../artifactShares';

const RELATIVE_SHARE_PATH = '/api/v1/public/artifact-share/abc.def';
const ABSOLUTE_SHARE_URL =
  'https://myrm-x.example.com/api/v1/public/artifact-share/abc.def';

describe('buildPublicArtifactShareUrl', () => {
  beforeEach(() => {
    mockBackendBase.value = '';
    vi.unstubAllGlobals();
  });

  it.each(['https://', 'http://'])(
    'passes through absolute server-provided %s share URLs untouched',
    (scheme) => {
      const url = `${scheme}myrm-x.example.com${RELATIVE_SHARE_PATH}`;
      expect(buildPublicArtifactShareUrl(url)).toBe(url);
    },
  );

  it('prefers the configured backend base over the browser origin', () => {
    mockBackendBase.value = 'https://backend.example.com';
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    expect(buildPublicArtifactShareUrl(RELATIVE_SHARE_PATH)).toBe(
      `https://backend.example.com${RELATIVE_SHARE_PATH}`,
    );
  });

  it('falls back to the current origin when no backend base is configured', () => {
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    expect(buildPublicArtifactShareUrl(RELATIVE_SHARE_PATH)).toBe(
      `http://localhost:3000${RELATIVE_SHARE_PATH}`,
    );
  });
});
