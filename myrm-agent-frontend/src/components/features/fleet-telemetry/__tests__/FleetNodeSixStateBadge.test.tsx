/** @vitest-environment jsdom */

/**
 * [INPUT]
 * - @/components/features/fleet-telemetry/FleetNodeSixStateBadge::FleetNodeSixStateBadge
 *
 * [OUTPUT]
 * - FleetNodeSixStateBadge 单元测试套件
 *
 * [POS]
 * tests/components/features/fleet-telemetry/__tests__/FleetNodeSixStateBadge.test.tsx
 * 验证分布式机队六态健康徽章渲染与排障诊断弹窗唤起交互。
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FleetNodeSixStateBadge } from '../FleetNodeSixStateBadge';
import type { FleetDiagnoseParams } from '@/services/fleetTelemetry';

vi.mock('@/services/fleetTelemetry', async () => {
  const actual = await vi.importActual('@/services/fleetTelemetry');
  return {
    ...actual,
    diagnoseFleetNode: vi.fn().mockResolvedValue({
      node_id: 'node-test',
      node_name: 'Tony-Mac',
      state: 'online',
      root_cause: '健康',
      recommended_action: '无',
      stages: [],
      diagnosed_at: 1000,
    }),
  };
});

describe('FleetNodeSixStateBadge Component', () => {
  const defaultParams: FleetDiagnoseParams = {
    node_id: 'n-1',
    node_name: 'Mac-Worker-01',
    host: '192.168.1.101',
    port: 8000,
    provider_name: 'Anthropic',
    model_name: 'claude-3-5-sonnet',
  };

  it('renders online state with healthy green style', () => {
    render(<FleetNodeSixStateBadge state="online" nodeParams={defaultParams} />);
    expect(screen.getByText('在线运行')).toBeInTheDocument();
  });

  it('renders provider_unavailable state accurately with credit issue warning', () => {
    render(<FleetNodeSixStateBadge state="provider_unavailable" nodeParams={defaultParams} />);
    // 必须精准显示模型欠费/超限，绝不能含糊报“连接断开”
    expect(screen.getByText('⚠️ 模型欠费/超限')).toBeInTheDocument();
  });

  it('renders gateway_stopped state accurately', () => {
    render(<FleetNodeSixStateBadge state="gateway_stopped" nodeParams={defaultParams} />);
    expect(screen.getByText('守护进程停止')).toBeInTheDocument();
  });

  it('opens diagnosis modal upon click', () => {
    render(<FleetNodeSixStateBadge state="provider_unavailable" nodeParams={defaultParams} />);
    const badgeBtn = screen.getByRole('button');
    fireEvent.click(badgeBtn);

    // 模态框打开并渲染五级探针标题
    expect(screen.getByText(/节点自省诊断 · Mac-Worker-01/)).toBeInTheDocument();
    expect(screen.getByText('五级排障自省探针')).toBeInTheDocument();
    expect(screen.getByText(/物理网络连通性/)).toBeInTheDocument();
    expect(screen.getByText(/上游模型配额与额度/)).toBeInTheDocument();
  });
});
