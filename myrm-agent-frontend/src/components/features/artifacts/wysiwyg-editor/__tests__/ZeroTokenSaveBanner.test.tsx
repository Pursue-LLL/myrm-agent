import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ZeroTokenSaveBanner } from '../ZeroTokenSaveBanner';
import { useWysiwygEditorStore } from '../useWysiwygEditorStore';
import { ZeroTokenCommitReport } from '../wysiwygEditorTypes';

describe('ZeroTokenSaveBanner', () => {
  beforeEach(() => {
    act(() => {
      useWysiwygEditorStore.getState().reset();
    });
  });

  it('在无提交保存报告时不渲染任何 DOM', () => {
    render(<ZeroTokenSaveBanner />);
    expect(
      screen.queryByTestId('zero-token-save-banner')
    ).not.toBeInTheDocument();
  });

  it('正确呈现工件版本、0 Token 标识、毫秒级耗时与上下文对账提示', () => {
    const mockReport: ZeroTokenCommitReport = {
      version: 2,
      savedAt: Date.now(),
      latencyMs: 18,
      tokenSavedCount: 2450,
      mutationCount: 2,
      contextIngressPrompt:
        '[用户在预览区就地微调了 2 处 DOM：h2.title 调整为「飞书知识库」]',
    };

    act(() => {
      useWysiwygEditorStore.setState({ lastCommitReport: mockReport });
    });

    render(<ZeroTokenSaveBanner />);

    expect(
      screen.getByTestId('zero-token-save-banner')
    ).toBeInTheDocument();
    expect(
      screen.getByText('工件版本 v2 就地极速保存成功')
    ).toBeInTheDocument();
    expect(screen.getByText('0 Token 消耗')).toBeInTheDocument();
    expect(screen.getByText('18ms')).toBeInTheDocument();
    expect(screen.getByText(/~2450/)).toBeInTheDocument();
    expect(
      screen.getByText(/用户在预览区就地微调了 2 处 DOM/)
    ).toBeInTheDocument();
  });
});
