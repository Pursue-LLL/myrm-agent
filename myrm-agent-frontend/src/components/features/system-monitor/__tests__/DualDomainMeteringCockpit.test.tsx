import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DualDomainMeteringCockpit } from '../DualDomainMeteringCockpit';
import {
  DomainMeteringRecordItem,
  ReconciliationStatementItem,
  SessionDualDomainSummaryItem,
} from '../dualDomainMeteringTypes';

describe('DualDomainMeteringCockpit Component', () => {
  const mockSummary: SessionDualDomainSummaryItem = {
    session_id: 'sess-corp-88',
    gateway_token_cost_usd: 0.012,
    sandbox_compute_cost_usd: 0.003,
    thirdparty_tool_cost_usd: 0.005,
    total_cost_usd: 0.02,
    total_operations: 3,
    gateway_ops_count: 1,
    sandbox_ops_count: 2,
    gateway_cost_ratio: 0.6,
    sandbox_cost_ratio: 0.4,
    generated_at_ms: 1719000000000,
  };

  const mockRecords: DomainMeteringRecordItem[] = [
    {
      record_id: 'rec-gw-1',
      session_id: 'sess-corp-88',
      domain: 'gateway_domain',
      operation_name: 'llm_chat_completion',
      resource_units: 4000.0,
      cost_breakdown: {
        model_token_cost_usd: 0.012,
        sandbox_compute_cost_usd: 0.0,
        thirdparty_tool_cost_usd: 0.0,
        total_cost_usd: 0.012,
      },
      billable: TrueOrBool(true),
      policy_note: 'Gateway Prompt & Output Tokens',
      timestamp_ms: 1719000001000,
    },
    {
      record_id: 'rec-sb-2',
      session_id: 'sess-corp-88',
      domain: 'sandbox_domain',
      operation_name: 'python_pandas_analysis',
      resource_units: 15.0,
      cost_breakdown: {
        model_token_cost_usd: 0.0,
        sandbox_compute_cost_usd: 0.003,
        thirdparty_tool_cost_usd: 0.0,
        total_cost_usd: 0.003,
      },
      billable: TrueOrBool(true),
      policy_note: 'Isolated Container CPU/RAM Compute',
      timestamp_ms: 1719000002000,
    },
    {
      record_id: 'rec-tool-3',
      session_id: 'sess-corp-88',
      domain: 'sandbox_domain',
      operation_name: 'brave_web_search',
      resource_units: 1.0,
      cost_breakdown: {
        model_token_cost_usd: 0.0,
        sandbox_compute_cost_usd: 0.0,
        thirdparty_tool_cost_usd: 0.005,
        total_cost_usd: 0.005,
      },
      billable: TrueOrBool(true),
      policy_note: 'External Search API Surcharge',
      timestamp_ms: 1719000003000,
    },
  ];

  function TrueOrBool(val: boolean): boolean {
    return val;
  }

  const mockStatement: ReconciliationStatementItem = {
    statement_id: 'recon-sess-corp-88-1719000',
    session_id: 'sess-corp-88',
    summary: mockSummary,
    records: mockRecords,
    integrity_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    generated_at_ms: 1719000004000,
  };

  it('renders title, dual-domain boundary banner, and 3D cost cards', () => {
    render(
      <DualDomainMeteringCockpit
        summary={mockSummary}
        records={mockRecords}
      />
    );

    expect(screen.getByText('双域透明计量边界与三维穿透成本驾驶舱')).toBeInTheDocument();
    expect(screen.getByText('网关域 (Gateway): 按 Token 精确计量')).toBeInTheDocument();
    expect(screen.getByText('沙箱域 (Sandbox): 按容器算力租约/本地免计费')).toBeInTheDocument();

    expect(screen.getAllByText('$0.0200').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('$0.0120').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('$0.0030').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('$0.0050').length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText('网关域: 60.0%')).toBeInTheDocument();
    expect(screen.getByText('沙箱域: 40.0%')).toBeInTheDocument();
  });

  it('filters records table by domain', async () => {
    render(
      <DualDomainMeteringCockpit
        summary={mockSummary}
        records={mockRecords}
      />
    );

    expect(screen.getByText('llm_chat_completion')).toBeInTheDocument();
    expect(screen.getByText('python_pandas_analysis')).toBeInTheDocument();
    expect(screen.getByText('brave_web_search')).toBeInTheDocument();

    // Click filter to gateway_domain
    const gwBtn = screen.getByRole('button', { name: '网关域' });
    await React.act(async () => {
      fireEvent.click(gwBtn);
    });

    expect(screen.getByText('llm_chat_completion')).toBeInTheDocument();
    expect(screen.queryByText('python_pandas_analysis')).not.toBeInTheDocument();
    expect(screen.queryByText('brave_web_search')).not.toBeInTheDocument();

    // Click filter back to all
    const allBtn = screen.getByRole('button', { name: '全部' });
    await React.act(async () => {
      fireEvent.click(allBtn);
    });

    expect(screen.getByText('python_pandas_analysis')).toBeInTheDocument();
  });

  it('renders reconciliation statement and handles generate button callback', async () => {
    const handleGenerate = vi.fn();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(),
      },
    });

    render(
      <DualDomainMeteringCockpit
        summary={mockSummary}
        records={mockRecords}
        statement={mockStatement}
        onGenerateStatement={handleGenerate}
      />
    );

    expect(screen.getByText('企业财务合规对账凭据已签署 (Tamper-Proof Audit Statement)')).toBeInTheDocument();
    expect(screen.getByText(/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855/)).toBeInTheDocument();

    const generateBtn = screen.getByRole('button', { name: '生成合规对账单' });
    await React.act(async () => {
      fireEvent.click(generateBtn);
    });
    expect(handleGenerate).toHaveBeenCalledWith('sess-corp-88');

    const copyBtn = screen.getByRole('button', { name: '复制哈希' });
    await React.act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(mockStatement.integrity_sha256);
  });
});
