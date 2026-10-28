/**
 * lazy-monaco-editor 契约：Monaco 的主题是整页共享的，所以主题只能由包装统一决定（跟随应用明暗，
 * 调用方无法覆盖）。随包 Monaco 的登记顺序见 lazy-monaco-editor.loader.test.tsx。
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

interface StubProps {
  theme?: string;
  language?: string;
  original?: string;
}

const { appTheme } = vi.hoisted(() => ({ appTheme: { resolved: 'light' as string | undefined } }));

vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: appTheme.resolved }) }));

vi.mock('monaco-editor', () => ({ bundledMonaco: true }));

vi.mock('@monaco-editor/react', () => ({
  loader: { config: vi.fn() },
  Editor: (props: StubProps) => {
    return <div data-testid="editor" data-theme={props.theme} data-language={props.language} />;
  },
  DiffEditor: (props: StubProps) => {
    return <div data-testid="diff" data-theme={props.theme} data-original={props.original} />;
  },
}));

import { LazyMonacoDiffEditor, LazyMonacoEditor } from '../lazy-monaco-editor';

afterEach(() => {
  cleanup();
  appTheme.resolved = 'light';
});

describe('LazyMonacoEditor theme', () => {
  it.each([
    ['dark', 'vs-dark'],
    ['light', 'vs'],
    [undefined, 'vs'],
  ])('follows the app theme (%s)', async (resolved, expected) => {
    appTheme.resolved = resolved;

    render(<LazyMonacoEditor />);

    expect((await screen.findByTestId('editor')).dataset.theme).toBe(expected);
  });

  it('cannot be given a theme by the caller', async () => {
    appTheme.resolved = 'dark';
    const callerProps = { theme: 'hc-black' } as object;

    render(<LazyMonacoEditor {...callerProps} />);

    expect((await screen.findByTestId('editor')).dataset.theme).toBe('vs-dark');
  });

  it('passes the other props through', async () => {
    render(<LazyMonacoEditor language="json" />);

    expect((await screen.findByTestId('editor')).dataset.language).toBe('json');
  });
});

describe('LazyMonacoDiffEditor theme', () => {
  it.each([
    ['dark', 'vs-dark'],
    ['light', 'vs'],
    [undefined, 'vs'],
  ])('follows the app theme (%s)', async (resolved, expected) => {
    appTheme.resolved = resolved;

    render(<LazyMonacoDiffEditor />);

    expect((await screen.findByTestId('diff')).dataset.theme).toBe(expected);
  });

  it('cannot be given a theme by the caller', async () => {
    appTheme.resolved = 'dark';
    const callerProps = { theme: 'hc-black' } as object;

    render(<LazyMonacoDiffEditor {...callerProps} />);

    expect((await screen.findByTestId('diff')).dataset.theme).toBe('vs-dark');
  });

  it('passes the other props through', async () => {
    render(<LazyMonacoDiffEditor original="before" />);

    expect((await screen.findByTestId('diff')).dataset.original).toBe('before');
  });
});
