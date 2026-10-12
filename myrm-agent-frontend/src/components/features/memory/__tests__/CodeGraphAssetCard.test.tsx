/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CodeGraphAssetCard } from '../command-center/CodeGraphAssetCard';

const {
  mockGetCodeGraphAssetMetadata,
  mockScanWorkspaceCodeGraph,
  mockAnalyzeCodeImpact,
  mockQueryCodeSymbols,
} = vi.hoisted(() => ({
  mockGetCodeGraphAssetMetadata: vi.fn(),
  mockScanWorkspaceCodeGraph: vi.fn(),
  mockAnalyzeCodeImpact: vi.fn(),
  mockQueryCodeSymbols: vi.fn(),
}));

vi.mock('@/services/memory/codeGraph', () => ({
  getCodeGraphAssetMetadata: mockGetCodeGraphAssetMetadata,
  scanWorkspaceCodeGraph: mockScanWorkspaceCodeGraph,
  analyzeCodeImpact: mockAnalyzeCodeImpact,
  queryCodeSymbols: mockQueryCodeSymbols,
}));

describe('CodeGraphAssetCard', () => {
  const mockAsset = {
    repo_id: 'myrm_workspace',
    version_hash: 'a1b2c3d4e5f67890',
    total_symbols: 42,
    total_edges: 98,
    updated_at: 1728300000,
  };

  const mockSymbols = [
    {
      symbol_id: 'module_a.py::helper_calculate',
      name: 'helper_calculate',
      kind: 'FUNCTION',
      file_path: 'module_a.py',
      line_start: 10,
      line_end: 25,
      parameters: ['x', 'y'],
      return_type: 'int',
      docstring: 'Core utility calculation helper.',
    },
  ];

  const mockImpact = {
    target_symbol_id: 'module_a.py::helper_calculate',
    target_symbol_name: 'helper_calculate',
    file_path: 'module_a.py',
    blast_radius: 8,
    risk_level: 'HIGH',
    direct_callers: ['module_b.py::compute_metrics'],
    indirect_callers: ['module_b.py::run_pipeline'],
    affected_files: ['module_b.py'],
    safety_recommendations: ['Review caller signatures and return types.'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCodeGraphAssetMetadata.mockResolvedValue(mockAsset);
    mockQueryCodeSymbols.mockResolvedValue({
      total: 1,
      symbols: mockSymbols,
    });
    mockScanWorkspaceCodeGraph.mockResolvedValue({
      scanned_files_count: 4,
      indexed_symbols_count: 12,
      total_symbols: 42,
      repo_id: 'myrm_workspace',
      version_hash: 'a1b2c3d4',
    });
    mockAnalyzeCodeImpact.mockResolvedValue(mockImpact);
  });

  it('renders CodeGraph HUD metadata and symbol topology inspector', async () => {
    render(<CodeGraphAssetCard />);

    await waitFor(() => {
      expect(screen.getByText('代码图谱与修改影响面评估 (CodeGraph & Impact Analysis)')).toBeInTheDocument();
      expect(screen.getByText('myrm_workspace')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('98')).toBeInTheDocument();
      expect(screen.getByText('helper_calculate')).toBeInTheDocument();
      expect(screen.getByText('module_a.py:10')).toBeInTheDocument();
    });
  });

  it('autofills input and performs impact analysis when clicking symbol item', async () => {
    render(<CodeGraphAssetCard />);

    await waitFor(() => {
      expect(screen.getByText('helper_calculate')).toBeInTheDocument();
    });

    const symbolBtn = screen.getByRole('button', { name: /helper_calculate/i });
    fireEvent.click(symbolBtn);

    const symbolInput = screen.getByPlaceholderText(/待修改符号名/i);
    const fileInput = screen.getByPlaceholderText(/文件路径/i);

    expect(symbolInput).toHaveValue('helper_calculate');
    expect(fileInput).toHaveValue('module_a.py');

    const assessButton = screen.getByRole('button', { name: /评估影响面/i });
    expect(assessButton).not.toBeDisabled();

    fireEvent.click(assessButton);

    await waitFor(() => {
      expect(mockAnalyzeCodeImpact).toHaveBeenCalledWith({
        symbol_name: 'helper_calculate',
        file_path: 'module_a.py',
      });
      expect(screen.getByText('HIGH 高风险')).toBeInTheDocument();
      expect(screen.getByText(/module_b\.py::compute_metrics/)).toBeInTheDocument();
      expect(screen.getByText(/module_b\.py::run_pipeline/)).toBeInTheDocument();
      expect(
        screen.getByText(/Review caller signatures and return types/i),
      ).toBeInTheDocument();
    });
  });




  it('triggers incremental workspace scan when clicking scan button', async () => {
    render(<CodeGraphAssetCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /增量扫描工作区/i })).toBeInTheDocument();
    });

    const scanButton = screen.getByRole('button', { name: /增量扫描工作区/i });
    fireEvent.click(scanButton);

    await waitFor(() => {
      expect(mockScanWorkspaceCodeGraph).toHaveBeenCalledWith({
        workspace_dir: '.',
        incremental: true,
      });
      expect(
        screen.getByText(/扫描完成：解析 4 个文件，更新 12 个符号/i),
      ).toBeInTheDocument();
    });
  });
});
