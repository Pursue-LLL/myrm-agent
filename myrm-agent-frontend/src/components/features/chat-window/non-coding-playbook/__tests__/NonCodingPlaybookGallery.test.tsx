import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { NonCodingPlaybookGallery } from '../NonCodingPlaybookGallery';
import { useNonCodingPlaybookStore } from '../useNonCodingPlaybookStore';

describe('NonCodingPlaybookGallery', () => {
  beforeEach(() => {
    useNonCodingPlaybookStore.getState().reset();
  });

  it('renders gallery header, comparison button, and scenario cards', () => {
    render(<NonCodingPlaybookGallery />);

    expect(
      screen.getByTestId('non-coding-playbook-gallery'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('非编码日常任务工作流画廊'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('与网页 Chat 相比有何优势？'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('智能发票报销整理与合规查重'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('复杂跨部门会议纪要转责任待办'),
    ).toBeInTheDocument();
  });

  it('filters scenarios by clicking category tab', () => {
    render(<NonCodingPlaybookGallery />);

    // 点击“财务发票”分类
    const financeTab = screen.getByRole('button', { name: '财务发票' });
    act(() => {
      fireEvent.click(financeTab);
    });

    expect(
      screen.getByText('智能发票报销整理与合规查重'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('复杂跨部门会议纪要转责任待办'),
    ).toBeNull();
  });

  it('searches scenarios by keyword', () => {
    render(<NonCodingPlaybookGallery />);

    const searchInput = screen.getByPlaceholderText(
      '搜索日常任务、工具或产出...',
    );
    act(() => {
      fireEvent.change(searchInput, { target: { value: '研报' } });
    });

    expect(
      screen.getByText('50页行业长研报跨文件精炼对比'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('智能发票报销整理与合规查重'),
    ).toBeNull();
  });

  it('triggers card click and calls onSelectScenario', () => {
    const handleSelect = vi.fn();
    render(<NonCodingPlaybookGallery onSelectScenario={handleSelect} />);

    const prefillBtns = screen.getAllByRole('button', {
      name: /一键配置并装填执行/,
    });
    expect(prefillBtns.length).toBeGreaterThan(0);

    const firstBtn = prefillBtns[0];
    if (firstBtn) {
      act(() => {
        fireEvent.click(firstBtn);
      });
    }

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(
      useNonCodingPlaybookStore.getState().activeScenarioModal,
    ).not.toBeNull();
  });

  it('opens comparison modal when why button is clicked', () => {
    render(<NonCodingPlaybookGallery />);

    const whyBtn = screen.getByRole('button', {
      name: '与网页 Chat 相比有何优势？',
    });
    act(() => {
      fireEvent.click(whyBtn);
    });

    expect(
      useNonCodingPlaybookStore.getState().isComparisonModalOpen,
    ).toBe(true);
  });
});
