import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DevLexiconBiasDrawer } from '../DevLexiconBiasDrawer';
import { useSpeechBiasStore } from '../useSpeechBiasStore';

describe('DevLexiconBiasDrawer', () => {
  beforeEach(() => {
    useSpeechBiasStore.getState().reset();
  });

  it('isDrawerOpen 为 false 时不渲染任何 DOM', () => {
    useSpeechBiasStore.setState({ isDrawerOpen: false });
    const { container } = render(<DevLexiconBiasDrawer />);

    expect(container.firstChild).toBeNull();
  });

  it('打开抽屉时正常渲染上下文状态与核心词汇', () => {
    useSpeechBiasStore.setState({
      isDrawerOpen: true,
      activeBranchName: 'feat/audio-bias',
      recentAstSymbols: ['useSpeechEngine', 'SpeechTokenExtractor'],
      installedSkills: ['agents-sdk'],
    });

    render(<DevLexiconBiasDrawer />);

    expect(screen.getByTestId('dev-lexicon-bias-drawer')).toBeInTheDocument();
    expect(screen.getByText('工程术语与声学偏置词典')).toBeInTheDocument();
    expect(screen.getByText(/分支: feat\/audio-bias/)).toBeInTheDocument();
    expect(screen.getByText(/AST 符号: 2 个/)).toBeInTheDocument();
    expect(screen.getByText(/激活技能: 1 个/)).toBeInTheDocument();
    expect(screen.getByText('grep')).toBeInTheDocument();
    expect(screen.getByText('pnpm')).toBeInTheDocument();
  });

  it('输入关键字过滤技术术语', () => {
    useSpeechBiasStore.setState({ isDrawerOpen: true });
    render(<DevLexiconBiasDrawer />);

    const searchInput = screen.getByPlaceholderText('搜索术语、易误听别名或分类...');
    fireEvent.change(searchInput, { target: { value: 'Kubernetes' } });

    expect(screen.getByText('Kubernetes')).toBeInTheDocument();
    expect(screen.queryByText('pnpm')).not.toBeInTheDocument();
  });

  it('通过表单新增自定义术语并展示在列表中', () => {
    useSpeechBiasStore.setState({ isDrawerOpen: true });
    render(<DevLexiconBiasDrawer />);

    const termInput = screen.getByPlaceholderText('标准技术术语 (如 pnpm)');
    const aliasInput = screen.getByPlaceholderText('常见语音误听词，逗号分隔 (如 屁恩屁恩, pen pm)');
    const submitBtn = screen.getByText('添加到本地偏置词典');

    fireEvent.change(termInput, { target: { value: 'MyrmidonCLI' } });
    fireEvent.change(aliasInput, { target: { value: '迈密顿命令行, myrmidon cli' } });
    fireEvent.click(submitBtn);

    expect(screen.getByText('MyrmidonCLI')).toBeInTheDocument();
    expect(screen.getByText('迈密顿命令行')).toBeInTheDocument();
  });

  it('点击关闭按钮关闭抽屉并触发 onClose 回调', () => {
    const handleClose = vi.fn();
    useSpeechBiasStore.setState({ isDrawerOpen: true });

    render(<DevLexiconBiasDrawer onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: '' });
    fireEvent.click(closeBtn);

    expect(useSpeechBiasStore.getState().isDrawerOpen).toBe(false);
    expect(handleClose).toHaveBeenCalled();
  });
});
