import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandCenterHudModal } from '../CommandCenterHudModal';
import { useCommandCenterHudStore } from '../useCommandCenterHudStore';

describe('CommandCenterHudModal', () => {
  beforeEach(() => {
    useCommandCenterHudStore.getState().reset();
  });

  it('renders nothing when isOpen is false', () => {
    render(<CommandCenterHudModal />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders modal with search, spend radar, doctor, and workstreams when open', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    expect(screen.getByRole('dialog', { name: '全局 Command Center HUD 运维大厅' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/穿透检索/)).toBeInTheDocument();
    expect(screen.getByText('算力消耗与热度大盘')).toBeInTheDocument();
    expect(screen.getByText('系统全面体检与就地自愈')).toBeInTheDocument();
    expect(screen.getByText(/周期内总 Token/)).toBeInTheDocument();
  });

  it('switches time ranges on button click', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const btn30d = screen.getByText('30D');
    fireEvent.click(btn30d);

    expect(useCommandCenterHudStore.getState().selectedTimeRange).toBe('30d');
  });

  it('executes doctor diagnostic run on button click', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const doctorBtn = screen.getByText('开始体检 (Doctor)');
    fireEvent.click(doctorBtn);

    expect(useCommandCenterHudStore.getState().isRunningDoctor).toBe(false);
  });

  it('executes auto remediation on remediable issue click', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const remediateBtn = screen.getByTitle('执行就地自愈修复');
    fireEvent.click(remediateBtn);

    expect(screen.getByText(/已就地自愈修复/)).toBeInTheDocument();
  });

  it('triggers configuration backup snapshot export', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const backupBtn = screen.getByText('导出快照');
    fireEvent.click(backupBtn);

    expect(screen.getByText(/快照生成成功/)).toBeInTheDocument();
  });

  it('filters workstreams via search input', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const input = screen.getByPlaceholderText(/穿透检索/);
    fireEvent.change(input, { target: { value: 'UI 原型' } });

    expect(screen.getByText('全栈电商营销活动 UI 原型设计')).toBeInTheDocument();
  });

  it('closes modal on close button click', () => {
    useCommandCenterHudStore.getState().openHud();
    render(<CommandCenterHudModal />);

    const closeBtn = screen.getByTitle('关闭 HUD (Esc)');
    fireEvent.click(closeBtn);

    expect(useCommandCenterHudStore.getState().isOpen).toBe(false);
  });
});
