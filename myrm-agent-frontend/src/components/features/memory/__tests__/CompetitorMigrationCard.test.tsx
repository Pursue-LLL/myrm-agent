/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SovereignMigrationInspectorCard } from '../command-center/SovereignMigrationInspectorCard';
import type {
  CompetitorDetectResponseDTO,
  CompetitorIngestResponseDTO,
  ExportBundleResponseDTO,
  RestoreBundleResponseDTO,
} from '@/services/memory/sovereignMigration';

const {
  mockExportSovereignBundle,
  mockRestoreSovereignBundle,
  mockDetectCompetitors,
  mockIngestCompetitor,
} = vi.hoisted(() => ({
  mockExportSovereignBundle: vi.fn(),
  mockRestoreSovereignBundle: vi.fn(),
  mockDetectCompetitors: vi.fn(),
  mockIngestCompetitor: vi.fn(),
}));

vi.mock('@/services/memory/sovereignMigration', () => ({
  exportSovereignBundle: mockExportSovereignBundle,
  restoreSovereignBundle: mockRestoreSovereignBundle,
  detectCompetitors: mockDetectCompetitors,
  ingestCompetitor: mockIngestCompetitor,
}));

describe('SovereignMigrationInspectorCard', () => {
  const mockExportData: ExportBundleResponseDTO = {
    success: true,
    bundle_path: '/tmp/exports/myrm-backup-20261008.myrmpkg',
    package_id: 'myrmpkg-20261008-a1b2c3d4',
    asset_count: 12,
    total_bytes: 1048576,
    sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  };

  const mockRestoreData: RestoreBundleResponseDTO = {
    success: true,
    package_id: 'myrmpkg-20261008-a1b2c3d4',
    restored_assets: ['memories/core.md', 'skills/deploy.py', 'rules/agent.yaml'],
    remapped_paths_count: 8,
    source_workspace_root: '/Users/old_mac/workspace',
    target_workspace_root: '/home/new_linux/workspace',
  };

  const mockDetectionData: CompetitorDetectResponseDTO = {
    detected_competitors: ['hermes', 'claude_code'],
    hermes_dir: '/Users/test/.hermes',
    claude_code_rule_path: '/Users/test/projects/CLAUDE.md',
    codex_rule_path: null,
  };

  const mockIngestData: CompetitorIngestResponseDTO = {
    success: true,
    imported_rules_count: 2,
    imported_skills_count: 5,
    imported_memories_count: 8,
    details: ['Ingested 8 memory files from Hermes into memories/', 'Preserved Hermes config.yaml as rules/hermes_config.yaml'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial tab buttons and export panel with accessible labels', () => {
    render(<SovereignMigrationInspectorCard />);

    expect(screen.getByText('全量数字资产主权打包、跨机无损还原与多源迁入')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '一键打包 (.myrmpkg)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '跨机还原 & 重定位' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '第三方智能体嗅探' })).toBeInTheDocument();

    expect(screen.getByLabelText(/源数据目录/)).toBeInTheDocument();
    expect(screen.getByLabelText(/目标归档文件路径/)).toBeInTheDocument();
    expect(screen.getByLabelText('归档备忘描述 (Description)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /一键生成主权便携包/ })).toBeInTheDocument();
  });

  it('handles sovereign bundle export', async () => {
    mockExportSovereignBundle.mockResolvedValueOnce(mockExportData);

    render(<SovereignMigrationInspectorCard />);

    const exportBtn = screen.getByRole('button', { name: /一键生成主权便携包/ });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(mockExportSovereignBundle).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/主权资产包打包成功！已生成 SHA-256 完整性指纹/)).toBeInTheDocument();
    expect(screen.getByText('myrmpkg-20261008-a1b2c3d4')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('handles sovereign bundle restore with dynamic path remapping', async () => {
    mockRestoreSovereignBundle.mockResolvedValueOnce(mockRestoreData);

    render(<SovereignMigrationInspectorCard />);

    const restoreTabBtn = screen.getByRole('button', { name: '跨机还原 & 重定位' });
    fireEvent.click(restoreTabBtn);

    const bundleInput = screen.getByLabelText('资产包文件路径 (Bundle Path)');
    fireEvent.change(bundleInput, { target: { value: '/tmp/backup.myrmpkg' } });

    const submitBtn = screen.getByRole('button', { name: /校验指纹并原子还原/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRestoreSovereignBundle).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/校验与还原成功！完成绝对路径动态重定位/)).toBeInTheDocument();
    expect(screen.getByText('还原资产: 3 项')).toBeInTheDocument();
    expect(screen.getByText('重映射路径: 8 处')).toBeInTheDocument();
  });

  it('handles competitor detection and one-click ingestion', async () => {
    mockDetectCompetitors.mockResolvedValueOnce(mockDetectionData);
    mockIngestCompetitor.mockResolvedValueOnce(mockIngestData);

    render(<SovereignMigrationInspectorCard />);

    const competitorTabBtn = screen.getByRole('button', { name: '第三方智能体嗅探' });
    fireEvent.click(competitorTabBtn);

    const probeBtn = screen.getByRole('button', { name: /嗅探本地第三方智能体资产/ });
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockDetectCompetitors).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('Hermes Agent')).toBeInTheDocument();
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('已探测到 2 处来源')).toBeInTheDocument();

    const ingestBtns = screen.getAllByRole('button', { name: /一键无损迁入 Myrm/ });
    expect(ingestBtns.length).toBe(2);

    fireEvent.click(ingestBtns[0]);

    await waitFor(() => {
      expect(mockIngestCompetitor).toHaveBeenCalledWith({
        competitor: 'hermes',
        source_path: '/Users/test/.hermes',
      });
    });

    expect(await screen.findByText(/迁入转换完成！数据资产已无损录入 Myrm 记忆与技能体系/)).toBeInTheDocument();
    expect(screen.getByText('记忆转译: 8 条')).toBeInTheDocument();
    expect(screen.getByText('技能转译: 5 个')).toBeInTheDocument();
    expect(screen.getByText('规则转译: 2 项')).toBeInTheDocument();
  });
});
