import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MultiArtboardCanvasViewport } from '../MultiArtboardCanvasViewport';
import { useMultiArtboardStore } from '../useMultiArtboardStore';

describe('MultiArtboardCanvasViewport', () => {
  beforeEach(() => {
    useMultiArtboardStore.getState().resetViewport();
    useMultiArtboardStore.getState().selectArtboard('artboard-home');
  });

  it('renders all artboard titles and dimensions', () => {
    render(<MultiArtboardCanvasViewport />);

    expect(screen.getByText('01 · 工作台首页')).toBeInTheDocument();
    expect(screen.getByText('02 · 日程排期表')).toBeInTheDocument();
    expect(screen.getByText('03 · 待办清单页')).toBeInTheDocument();
    expect(screen.getByText('04 · 偏好设置页')).toBeInTheDocument();
  });

  it('renders interactive button layers with flow hints', () => {
    render(<MultiArtboardCanvasViewport />);

    const scheduleBtn = screen.getByRole('button', { name: /查看今日日程/ });
    expect(scheduleBtn).toBeInTheDocument();

    const todoBtn = screen.getByRole('button', { name: /待办任务清单/ });
    expect(todoBtn).toBeInTheDocument();
  });

  it('handles artboard selection when clicking on artboard header', () => {
    render(<MultiArtboardCanvasViewport />);

    const scheduleHeader = screen.getByText('02 · 日程排期表');
    fireEvent.mouseDown(scheduleHeader, { clientX: 100, clientY: 100 });

    expect(useMultiArtboardStore.getState().selectedArtboardId).toBe('artboard-schedule');
  });

  it('handles layer selection when clicking a button layer', () => {
    render(<MultiArtboardCanvasViewport />);

    const btn = screen.getByRole('button', { name: /查看今日日程/ });
    fireEvent.click(btn);

    expect(useMultiArtboardStore.getState().selectedArtboardId).toBe('artboard-home');
    expect(useMultiArtboardStore.getState().selectedLayerId).toBe('btn-goto-schedule');
  });

  it('renders flow link labels when showFlowLinks is true', () => {
    useMultiArtboardStore.getState().toggleFlowLinks(true);
    render(<MultiArtboardCanvasViewport />);

    // SVG 连线中的文字标签
    expect(screen.getAllByText('查看今日日程 ➔').length).toBeGreaterThan(0);
  });
});
