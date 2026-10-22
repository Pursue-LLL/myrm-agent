import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DashboardWorkspaceDrawer } from '../DashboardWorkspaceDrawer';
import { useDashboardWorkspaceStore } from '../useDashboardWorkspaceStore';

describe('DashboardWorkspaceDrawer', () => {
  beforeEach(() => {
    useDashboardWorkspaceStore.getState().clearAllWidgets();
    useDashboardWorkspaceStore.getState().closeDrawer();
    useDashboardWorkspaceStore.getState().setSearchQuery('');
    useDashboardWorkspaceStore.getState().setActiveTagFilter(null);
  });

  it('renders nothing when drawer is closed', () => {
    const { container } = render(<DashboardWorkspaceDrawer />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders empty state when open with zero pinned widgets', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    render(<DashboardWorkspaceDrawer />);

    expect(screen.getByRole('dialog', { name: '数字员工监控工作台' })).toBeInTheDocument();
    expect(screen.getByText('工作台尚无固定组件')).toBeInTheDocument();
    expect(screen.getByText(/0 个组件/)).toBeInTheDocument();
  });

  it('renders pinned widgets in grid canvas with headers and actions', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-card-1',
      title: 'Sales Funnel',
      language: 'html',
      content: '<div>Sales Chart</div>',
      tags: ['html', 'chart'],
    });

    render(<DashboardWorkspaceDrawer />);

    expect(screen.getByText('Sales Funnel')).toBeInTheDocument();
    expect(screen.getByText(/1 个组件/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('搜索组件标题或内容...')).toBeInTheDocument();
  });

  it('filters widgets via search input and tag buttons', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-search-1',
      title: 'Alpha Widget',
      language: 'html',
      content: '<div>Alpha Content</div>',
      tags: ['alpha'],
    });
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-search-2',
      title: 'Beta Widget',
      language: 'svg',
      content: '<svg>Beta Content</svg>',
      tags: ['beta'],
    });

    render(<DashboardWorkspaceDrawer />);
    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    expect(screen.getByText('Beta Widget')).toBeInTheDocument();

    // Search filter
    const searchInput = screen.getByPlaceholderText('搜索组件标题或内容...');
    fireEvent.change(searchInput, { target: { value: 'Alpha' } });
    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    expect(screen.queryByText('Beta Widget')).not.toBeInTheDocument();

    // Reset search, test tag filter
    fireEvent.change(searchInput, { target: { value: '' } });
    const betaTagBtn = screen.getByRole('button', { name: /^beta$/i });
    fireEvent.click(betaTagBtn);

    expect(screen.queryByText('Alpha Widget')).not.toBeInTheDocument();
    expect(screen.getByText('Beta Widget')).toBeInTheDocument();
  });

  it('allows inline editing of widget title', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-edit-1',
      title: 'Initial Title',
      language: 'html',
      content: '<div>Widget</div>',
    });

    render(<DashboardWorkspaceDrawer />);
    const titleSpan = screen.getByText('Initial Title');
    fireEvent.click(titleSpan);

    const input = screen.getByDisplayValue('Initial Title');
    fireEvent.change(input, { target: { value: 'Renamed Funnel' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    expect(useDashboardWorkspaceStore.getState().widgets[0].title).toBe('Renamed Funnel');
    expect(screen.getByText('Renamed Funnel')).toBeInTheDocument();
  });

  it('cycles layout colSpan on button click', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-cycle-1',
      title: 'Cycle Layout Widget',
      language: 'html',
      content: '<div>Widget</div>',
      colSpan: '1',
    });

    render(<DashboardWorkspaceDrawer />);
    const cycleBtn = screen.getByTitle(/切换布局宽档/);

    // 1 -> 2
    fireEvent.click(cycleBtn);
    expect(useDashboardWorkspaceStore.getState().widgets[0].colSpan).toBe('2');

    // 2 -> 3
    fireEvent.click(cycleBtn);
    expect(useDashboardWorkspaceStore.getState().widgets[0].colSpan).toBe('3');

    // 3 -> 1
    fireEvent.click(cycleBtn);
    expect(useDashboardWorkspaceStore.getState().widgets[0].colSpan).toBe('1');
  });

  it('handles widget unpin and refresh actions', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    useDashboardWorkspaceStore.getState().pinWidget({
      id: 'w-action-1',
      title: 'Action Widget',
      language: 'html',
      content: '<div>Widget</div>',
    });

    render(<DashboardWorkspaceDrawer />);
    const unpinBtn = screen.getByTitle('取消固定');
    fireEvent.click(unpinBtn);

    expect(useDashboardWorkspaceStore.getState().widgets).toHaveLength(0);
    expect(screen.getByText('工作台尚无固定组件')).toBeInTheDocument();
  });

  it('closes drawer when close button clicked', () => {
    useDashboardWorkspaceStore.getState().openDrawer();
    render(<DashboardWorkspaceDrawer />);

    const closeBtn = screen.getByLabelText('关闭工作台');
    fireEvent.click(closeBtn);

    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(false);
  });
});
