import { describe, expect, it, vi } from 'vitest';

vi.mock('@/services/chat', () => ({
  getWorkspaceFileContentUrl: (path: string, workspace: string) =>
    `/content?path=${encodeURIComponent(path)}&workspace=${encodeURIComponent(workspace)}`,
}));
vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

import { resolveWorkspaceUrl } from '../resolveWorkspaceUrl';

const DOC = '/ws/docs/guide/intro.md';
const WORKSPACE = '/ws';

const contentOf = (path: string) => `/content?path=${encodeURIComponent(path)}&workspace=%2Fws`;

describe('resolveWorkspaceUrl', () => {
  it('points a relative address at the file beside the document', () => {
    expect(resolveWorkspaceUrl('logo.png', DOC, WORKSPACE)).toBe(contentOf('/ws/docs/guide/logo.png'));
    expect(resolveWorkspaceUrl('./img/logo.png', DOC, WORKSPACE)).toBe(contentOf('/ws/docs/guide/img/logo.png'));
  });

  it('walks up through ../ and never past the root of the path', () => {
    expect(resolveWorkspaceUrl('../shared/logo.png', DOC, WORKSPACE)).toBe(contentOf('/ws/docs/shared/logo.png'));
    expect(resolveWorkspaceUrl('../../../../../etc/passwd', DOC, WORKSPACE)).toBe(contentOf('/etc/passwd'));
  });

  it('decodes percent-encoding and ignores a query or fragment', () => {
    expect(resolveWorkspaceUrl('my%20image.png?raw=true', DOC, WORKSPACE)).toBe(
      contentOf('/ws/docs/guide/my image.png'),
    );
    expect(resolveWorkspaceUrl('notes.md#section', DOC, WORKSPACE)).toBe(contentOf('/ws/docs/guide/notes.md'));
    expect(resolveWorkspaceUrl('100%.png', DOC, WORKSPACE)).toBe(contentOf('/ws/docs/guide/100%.png'));
  });

  it('works for a Windows path, keeping its separators', () => {
    expect(resolveWorkspaceUrl('img/logo.png', 'C:\\ws\\docs\\intro.md', 'C:\\ws')).toBe(
      `/content?path=${encodeURIComponent('C:\\ws\\docs\\img\\logo.png')}&workspace=${encodeURIComponent('C:\\ws')}`,
    );
    expect(resolveWorkspaceUrl('..\\logo.png', 'C:\\ws\\docs\\intro.md', 'C:\\ws')).toBe(
      `/content?path=${encodeURIComponent('C:\\ws\\logo.png')}&workspace=${encodeURIComponent('C:\\ws')}`,
    );
  });

  it('leaves addresses that are not relative paths as they are', () => {
    for (const url of [
      'https://example.com/a.png',
      'http://example.com/a.png',
      'data:image/png;base64,AAAA',
      'blob:https://example.com/1',
      'mailto:someone@example.com',
      '#section',
      '//cdn.example.com/a.png',
      '/absolute/a.png',
      '',
    ]) {
      expect(resolveWorkspaceUrl(url, DOC, WORKSPACE)).toBe(url);
    }
  });
});
