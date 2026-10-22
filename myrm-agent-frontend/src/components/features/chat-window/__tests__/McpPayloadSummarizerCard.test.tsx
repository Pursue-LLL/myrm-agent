import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  McpPayloadSummarizerCard,
  McpSummaryArtifactData,
} from '../McpPayloadSummarizerCard';

describe('McpPayloadSummarizerCard', () => {
  const mockArtifact: McpSummaryArtifactData = {
    artifact_id: 'mcp-summary-test1',
    source_tool_or_mcp: 'figma_canvas_exporter',
    raw_payload_bytes: 12000,
    summary_bytes: 1800,
    token_saving_ratio: 0.85,
    summary_text: '### MCP Response Summary from `figma_canvas_exporter`\n- Total Root Keys: 3',
    extracted_fields: { title: 'Figma Canvas Document Bulk Export' },
    file_reference_path: '/tmp/figma_dump.json',
    created_at: '2026-10-15T12:00:00Z',
  };

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/mcp-summarizer/preset')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                name: 'mcp-data-summarizer',
                description: 'Dedicated isolated subagent fetching heavy MCP payloads',
                tools_whitelist: ['read_file', 'write_file', 'search_web'],
              },
            }),
          });
        }
        if (url.includes('/mcp-summarizer/summarize')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: mockArtifact,
            }),
          });
        }
        if (url.includes('/mcp-summarizer/diagnose')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                risk_level: 'severe_contamination',
                payload_bytes: 25000,
                estimated_tokens: 6250,
                is_isolated_via_subagent: false,
                remediation_advice: 'Severe Contamination Risk: enforce mcp-data-summarizer delegation',
                detected_at: '2026-10-15T12:01:00Z',
              },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ data: {} }),
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders card with initial artifact and handles dismiss', async () => {
    const handleDismiss = vi.fn();

    await act(async () => {
      render(
        <McpPayloadSummarizerCard
          initialArtifact={mockArtifact}
          onDismiss={handleDismiss}
        />,
      );
    });

    expect(screen.getByText('重 Payload MCP 摘要回传')).toBeInTheDocument();
    expect(screen.getByText('figma_canvas_exporter')).toBeInTheDocument();
    expect(screen.getByText('节省 85.0% Tokens')).toBeInTheDocument();
    expect(screen.getByText(/Total Root Keys: 3/)).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('runs summary simulation when button is clicked', async () => {
    await act(async () => {
      render(<McpPayloadSummarizerCard />);
    });

    const simulateBtn = screen.getByRole('button', { name: '提取结构化摘要演练' });
    await act(async () => {
      fireEvent.click(simulateBtn);
    });

    expect(screen.getByText('成功生成结构化摘要工件')).toBeInTheDocument();
    expect(screen.getByText('figma_canvas_exporter')).toBeInTheDocument();
  });

  it('switches to doctor tab and runs contamination diagnostic audit', async () => {
    await act(async () => {
      render(<McpPayloadSummarizerCard />);
    });

    const doctorTab = screen.getByRole('button', { name: '污染审计' });
    fireEvent.click(doctorTab);

    expect(screen.getByText('Context Contamination 门禁规则')).toBeInTheDocument();

    const auditBtn = screen.getByRole('button', { name: '检测当前会话污染风险' });
    await act(async () => {
      fireEvent.click(auditBtn);
    });

    expect(screen.getByText('严重上下文污染 (SEVERE)')).toBeInTheDocument();
    expect(screen.getByText(/Severe Contamination Risk/)).toBeInTheDocument();
  });

  it('switches to preset tab and handles apply callback', async () => {
    const handleApply = vi.fn();

    await act(async () => {
      render(<McpPayloadSummarizerCard onApplySubagentPreset={handleApply} />);
    });

    const presetTab = screen.getByRole('button', { name: '专属子Agent' });
    fireEvent.click(presetTab);

    expect(screen.getByText('mcp-data-summarizer')).toBeInTheDocument();
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText('write_file')).toBeInTheDocument();

    const applyBtn = screen.getByRole('button', { name: '一键绑定至当前会话' });
    fireEvent.click(applyBtn);
    expect(handleApply).toHaveBeenCalledTimes(1);
  });
});
