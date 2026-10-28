/**
 * 随包的 Monaco 必须在编辑器渲染前登记给 `@monaco-editor/react` 的 loader，否则编辑器会回退到 CDN
 * （离线时一直停在 Loading）。懒加载每种编辑器只解析一次，所以每个用例都得是本文件里该种编辑器的第一次渲染，
 * 不要在这里再加渲染同一种编辑器的用例。
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { events } = vi.hoisted(() => ({ events: [] as string[] }));

vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));

vi.mock('monaco-editor', () => ({ bundledMonaco: true }));

vi.mock('@monaco-editor/react', () => ({
  loader: {
    config: (options: { monaco?: { bundledMonaco?: boolean } }) => {
      events.push(options.monaco?.bundledMonaco ? 'config:bundled' : 'config:other');
    },
  },
  Editor: () => {
    events.push('render:editor');
    return <div data-testid="editor" />;
  },
  DiffEditor: () => {
    events.push('render:diff');
    return <div data-testid="diff" />;
  },
}));

import { LazyMonacoDiffEditor, LazyMonacoEditor } from '../lazy-monaco-editor';

afterEach(() => {
  cleanup();
  events.length = 0;
});

describe('bundled Monaco', () => {
  it('is handed to the loader before the editor renders', async () => {
    render(<LazyMonacoEditor />);
    await screen.findByTestId('editor');

    expect(events[0]).toBe('config:bundled');
    expect(events).toContain('render:editor');
  });

  it('is handed to the loader before the diff editor renders', async () => {
    render(<LazyMonacoDiffEditor />);
    await screen.findByTestId('diff');

    expect(events[0]).toBe('config:bundled');
    expect(events).toContain('render:diff');
  });
});
