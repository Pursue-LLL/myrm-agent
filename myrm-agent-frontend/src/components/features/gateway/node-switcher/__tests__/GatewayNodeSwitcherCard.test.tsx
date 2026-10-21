import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GatewayNodeSwitcherCard } from '../GatewayNodeSwitcherCard';
import { useGatewayNodeStore } from '../useGatewayNodeStore';

describe('GatewayNodeSwitcherCard', () => {
  beforeEach(() => {
    useGatewayNodeStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('正确渲染主连节点徽标与节点卡片列表', () => {
    render(<GatewayNodeSwitcherCard />);

    expect(screen.getByTestId('gateway-node-switcher-card')).toBeInTheDocument();
    expect(screen.getByTestId('current-active-badge')).toHaveTextContent(
      '主连: 本地开发主力机 (Localhost)'
    );

    expect(
      screen.getByTestId('gateway-node-card-node-localhost-01')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('gateway-node-card-node-gpu-vps-02')
    ).toBeInTheDocument();
  });

  it('点击“设为主节点”能够将对应节点切换为当前主连', () => {
    render(<GatewayNodeSwitcherCard />);

    const switchBtn = screen.getByTestId('switch-node-btn-node-gpu-vps-02');
    fireEvent.click(switchBtn);

    expect(useGatewayNodeStore.getState().activeNodeId).toBe('node-gpu-vps-02');
    expect(screen.getByTestId('current-active-badge')).toHaveTextContent(
      '主连: 机房远程 GPU 算力节点'
    );
  });

  it('在搜索框输入关键词后能即时筛选对应节点', () => {
    render(<GatewayNodeSwitcherCard />);

    const searchInput = screen.getByPlaceholderText(/搜索节点名称/);
    fireEvent.change(searchInput, { target: { value: 'NAS' } });

    expect(
      screen.getByTestId('gateway-node-card-node-home-nas-03')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('gateway-node-card-node-localhost-01')
    ).not.toBeInTheDocument();
  });

  it('点击添加宿主节点按钮可打开模态框，填写并提交新节点', () => {
    render(<GatewayNodeSwitcherCard />);

    const openModalBtn = screen.getByTestId('open-add-modal-btn');
    fireEvent.click(openModalBtn);

    expect(screen.getByTestId('add-node-dialog')).toBeInTheDocument();

    const nameInput = screen.getByLabelText('宿主节点名称');
    const urlInput = screen.getByLabelText('网关 API Endpoint 地址');
    const submitBtn = screen.getByTestId('submit-add-node-btn');

    fireEvent.change(nameInput, { target: { value: '实验室超算节点' } });
    fireEvent.change(urlInput, { target: { value: 'http://10.200.0.1:8000' } });
    fireEvent.click(submitBtn);

    const nodes = useGatewayNodeStore.getState().nodes;
    const added = nodes.find((n) => n.name === '实验室超算节点');
    expect(added).toBeDefined();
    expect(added?.endpointUrl).toBe('http://10.200.0.1:8000');
  });

  it('点击探活按钮可平稳触发节点健康探测', async () => {
    render(<GatewayNodeSwitcherCard />);

    const probeBtn = screen.getByTestId('probe-btn-node-localhost-01');
    fireEvent.click(probeBtn);

    const probeAllBtn = screen.getByTestId('probe-all-btn');
    fireEvent.click(probeAllBtn);
  });
});
