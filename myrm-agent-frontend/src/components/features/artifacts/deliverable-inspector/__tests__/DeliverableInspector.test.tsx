import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DeliverableInspector } from '../DeliverableInspector';

describe('DeliverableInspector', () => {
  const mockSlidesContent = `
# 标题页：年度回顾
2026 全面复盘

---
## 第二页：核心指标
- 营收 +150%
- 活跃用户创历史新高

---
## 第三页：未来展望
- 推进 Agent 自进化架构
  `.trim();

  it('renders initial deliverable inspector with parsed nodes and v1 badge', () => {
    render(
      <DeliverableInspector
        rawContent={mockSlidesContent}
        deliverableType="slides"
        artifactTitle="2026 年度汇报 PPT"
      />,
    );

    expect(screen.getByText('2026 年度汇报 PPT')).toBeDefined();
    expect(screen.getByText('v1')).toBeDefined();
    expect(screen.getByText('3 节点')).toBeDefined();
    expect(screen.getAllByText('标题页：年度回顾').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('第二页：核心指标')).toBeDefined();
  });

  it('switches active node when selecting from outline navigator', () => {
    render(
      <DeliverableInspector
        rawContent={mockSlidesContent}
        deliverableType="slides"
        artifactTitle="2026 年度汇报 PPT"
      />,
    );

    const secondNodeBtn = screen.getByText('第二页：核心指标');
    fireEvent.click(secondNodeBtn);

    expect(screen.getByText(/局部针对性重做：第二页：核心指标/)).toBeDefined();
  });

  it('applies selective partial patch and increments version snapshot', async () => {
    const onPatchCommit = vi.fn();
    render(
      <DeliverableInspector
        rawContent={mockSlidesContent}
        deliverableType="slides"
        artifactTitle="2026 年度汇报 PPT"
        onPatchCommit={onPatchCommit}
      />,
    );

    // Switch to second node
    fireEvent.click(screen.getByText('第二页：核心指标'));

    // Input targeted prompt in patch bar
    const input = screen.getByPlaceholderText(/输入微调要求/);
    fireEvent.change(input, { target: { value: '将指标改为柱状图展示' } });

    const submitBtn = screen.getByRole('button', { name: /定向重做/i });
    fireEvent.click(submitBtn);

    // Wait for patch to commit and version to bump to v2
    await waitFor(() => {
      expect(screen.getByText('v2')).toBeDefined();
    });

    expect(onPatchCommit).toHaveBeenCalledTimes(1);
    expect(screen.getByText('版本对比 (2)')).toBeDefined();
  });

  it('opens version diff modal and handles rollback', async () => {
    const onRollbackCommit = vi.fn();
    render(
      <DeliverableInspector
        rawContent={mockSlidesContent}
        deliverableType="slides"
        artifactTitle="2026 年度汇报 PPT"
        onRollbackCommit={onRollbackCommit}
      />,
    );

    // Patch node to get to v2
    const input = screen.getByPlaceholderText(/输入微调要求/);
    fireEvent.change(input, { target: { value: '第一页文案精简' } });
    fireEvent.click(screen.getByRole('button', { name: /定向重做/i }));

    await waitFor(() => {
      expect(screen.getByText('v2')).toBeDefined();
    });

    // Open diff modal
    const diffBtn = screen.getByRole('button', { name: /版本对比/i });
    fireEvent.click(diffBtn);

    expect(screen.getByText('版本快照对比与安全回退')).toBeDefined();

    // Select v1 chip and click rollback
    fireEvent.click(screen.getByRole('button', { name: /^v1/i }));
    const rollbackBtn = screen.getByRole('button', { name: /无损回退到 v1/i });
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(onRollbackCommit).toHaveBeenCalledTimes(1);
    });
  });

  it('toggles fullscreen inspection mode', () => {
    render(
      <DeliverableInspector
        rawContent={mockSlidesContent}
        deliverableType="slides"
        artifactTitle="2026 年度汇报 PPT"
      />,
    );

    const toggleBtn = screen.getByRole('button', { name: '全屏核验' });
    fireEvent.click(toggleBtn);

    expect(screen.getByRole('button', { name: '退出全屏' })).toBeDefined();
  });
});
