import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SinglePassRichStreamViewer } from '../SinglePassRichStreamViewer';
import { StreamPerformanceBenchmarkModal } from '../StreamPerformanceBenchmarkModal';
import { useStreamProtocolStore } from '../useStreamProtocolStore';

describe('SinglePassRichStreamViewer & StreamPerformanceBenchmarkModal Components', () => {
  beforeEach(() => {
    useStreamProtocolStore.getState().resetStream();
    // Mock navigator.clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });
  });

  describe('SinglePassRichStreamViewer', () => {
    it('renders top telemetry bar and default rich stream content', () => {
      useStreamProtocolStore.getState().setStreamContent(`Hello **World** from single-pass stream!

\`\`\`typescript
const greeting = "Hello Myrm";
\`\`\`

\x1b[32m[PASS]\x1b[0m All tests green.`);

      render(<SinglePassRichStreamViewer />);

      expect(screen.getByText(/单遍流式引擎/)).toBeDefined();
      expect(screen.getByText(/Token\/s/)).toBeDefined();
      expect(screen.getAllByText(/Hello/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('World')).toBeDefined();
      expect(screen.getByText('typescript')).toBeDefined();
      expect(screen.getByText('[PASS]')).toBeDefined();
      expect(screen.getByRole('button', { name: /性能对比看板/ })).toBeDefined();
    });

    it('copies code block content on click', async () => {
      useStreamProtocolStore.getState().setStreamContent(`\`\`\`python
def test_func():
  return True
\`\`\``);

      render(<SinglePassRichStreamViewer />);

      const copyBtn = screen.getByRole('button', { name: /复制代码/ });
      expect(copyBtn).toBeDefined();
      fireEvent.click(copyBtn);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('def test_func():\n  return True');
      expect(screen.getByText(/已复制/)).toBeDefined();
    });

    it('shows floating re-anchor CTA button when user is detached', () => {
      useStreamProtocolStore.getState().setStreamContent('Paragraph 1\n'.repeat(20));
      useStreamProtocolStore.getState().handleContentGrow(2000);

      render(<SinglePassRichStreamViewer />);

      // 模拟用户向上翻看 (scrollHeight=2000, scrollTop=50, clientHeight=600 -> distance=1350 > 32)
      act(() => {
        useStreamProtocolStore.getState().handleScroll(50);
      });

      const reanchorBtn = screen.getByRole('button', { name: /回到底部追踪/ });
      expect(reanchorBtn).toBeDefined();
      fireEvent.click(reanchorBtn);
    });
  });

  describe('StreamPerformanceBenchmarkModal', () => {
    it('does not render when modal is closed', () => {
      render(<StreamPerformanceBenchmarkModal />);
      expect(screen.queryByText(/流式渲染性能基准对比/)).toBeNull();
    });

    it('renders comparison cards and benchmark metrics when opened', () => {
      useStreamProtocolStore.getState().setStreamContent('Benchmarking stream tokens.');
      useStreamProtocolStore.getState().openBenchmarkModal();

      render(<StreamPerformanceBenchmarkModal />);

      expect(screen.getByText(/流式渲染性能基准对比/)).toBeDefined();
      expect(screen.getByText('传统多轮全量正则')).toBeDefined();
      expect(screen.getByText('Myrm 单遍流式引擎')).toBeDefined();
      expect(screen.getByText(/~267,000 ms/)).toBeDefined();
      expect(screen.getByText(/降至 ~90ms/)).toBeDefined();
      expect(screen.getByText(/TLA\+ 弹性槽位/)).toBeDefined();
      expect(screen.getByText(/~2,960x 提速/)).toBeDefined();

      // 点击重新采样
      const resampleBtn = screen.getByRole('button', { name: /重新采样测试/ });
      fireEvent.click(resampleBtn);

      // 点击关闭
      const closeButtons = screen.getAllByRole('button');
      const closeBtn = closeButtons[0]; // 右上角 X
      fireEvent.click(closeBtn);
      expect(useStreamProtocolStore.getState().isBenchmarkModalOpen).toBe(false);
    });
  });
});
