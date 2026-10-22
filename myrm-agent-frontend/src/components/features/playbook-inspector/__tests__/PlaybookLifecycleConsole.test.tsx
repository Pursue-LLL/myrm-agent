import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlaybookLifecycleConsole } from '../PlaybookLifecycleConsole';
import { usePlaybookInspectorStore } from '../usePlaybookInspectorStore';

describe('PlaybookLifecycleConsole', () => {
  beforeEach(() => {
    usePlaybookInspectorStore.getState().reset();
    vi.restoreAllMocks();
  });

  it('renders header, filter tabs and initial default rules', () => {
    render(<PlaybookLifecycleConsole />);
    expect(screen.getByText('判断力规约生命周期看板')).toBeDefined();
    expect(screen.getByText('人类最高仲裁权')).toBeDefined();
    expect(screen.getByText(/全部/)).toBeDefined();
    expect(screen.getAllByText(/生效中/).length).toBeGreaterThan(0);
    expect(screen.getByText('TypeScript 严格类型防御与禁用 any')).toBeDefined();
  });

  it('filters rules by status when tab clicked', () => {
    render(<PlaybookLifecycleConsole />);
    const retiredTab = screen.getByRole('button', { name: /已退役/ });
    fireEvent.click(retiredTab);

    expect(screen.queryByText('TypeScript 严格类型防御与禁用 any')).toBeNull();
    expect(screen.getByText('执行任务后自动删除临时调试文件')).toBeDefined();
  });

  it('filters rules by search query input', () => {
    render(<PlaybookLifecycleConsole />);
    const searchInput = screen.getByRole('textbox', { name: /搜索规约/ });
    fireEvent.change(searchInput, { target: { value: '400 行' } });

    expect(screen.getByText('单文件 400 行严格行数边界控制与模块化拆分')).toBeDefined();
    expect(screen.queryByText('TypeScript 严格类型防御与禁用 any')).toBeNull();
  });

  it('opens add modal and creates new custom rule', () => {
    render(<PlaybookLifecycleConsole />);
    const newRuleBtn = screen.getByRole('button', { name: /新建规约/ });
    fireEvent.click(newRuleBtn);

    const titleInput = screen.getByRole('textbox', { name: /规约标题/ });
    const directiveInput = screen.getByRole('textbox', { name: /规约指令内容/ });
    fireEvent.change(titleInput, { target: { value: '前端零原生 emoji 规范' } });
    fireEvent.change(directiveInput, { target: { value: '必须全部使用 Lucide 图标' } });

    const createBtn = screen.getByRole('button', { name: /创建并锁定/ });
    fireEvent.click(createBtn);

    expect(screen.getByText('前端零原生 emoji 规范')).toBeDefined();
  });
});
