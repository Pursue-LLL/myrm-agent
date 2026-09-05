import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LocalSkillPathScanPreviewBeforeAdoptDialog } from '../LocalSkillPathScanPreviewBeforeAdoptDialog';
import type { LocalSkillPathPreviewResponse } from '@/store/skill/types';

const mockTranslations: Record<string, string> = {
  'previewDialog.title': '本地技能路径预检与采纳',
  'previewDialog.description': '在正式添加该路径前，请确认已发现的技能条目、安全性与同名冲突。',
  'previewDialog.resolvedPath': '物理绝对路径',
  'previewDialog.discoveredCount': '已发现技能',
  'previewDialog.noSkillsFound': '未发现有效技能',
  'previewDialog.noSkillsFoundDesc': '该路径下未找到包含标准 SKILL.md 的有效技能目录。',
  'previewDialog.conflicted': '同名冲突',
  'previewDialog.safe': '安全无风险',
  'previewDialog.warning': '潜在安全风险',
  'previewDialog.cancel': '取消',
  'previewDialog.adopt': '确认采纳并保存路径',
  'previewDialog.adopting': '采纳保存中...',
  'previewDialog.addPathOnly': '仅添加路径',
  'previewDialog.selectAll': '全选',
  'previewDialog.deselectAll': '全不选',
  'previewDialog.selectedCount': '已选择技能',
  'previewDialog.tools': '依赖工具',
};

const stableT = (key: string, params?: { count?: number }) => {
  if (params?.count !== undefined) {
    return `${mockTranslations[key] ?? key} (${params.count})`;
  }
  return mockTranslations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('LocalSkillPathScanPreviewBeforeAdoptDialog Component Tests', () => {
  const onOpenChange = vi.fn();
  const onConfirmAdopt = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders null when previewData is null', () => {
    const { container } = render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={null}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders empty state and disables adopt button when 0 skills discovered', () => {
    const emptyPreview: LocalSkillPathPreviewResponse = {
      resolved_path: '/home/user/empty-skills',
      exists: true,
      is_directory: true,
      total_discovered: 0,
      skills: [],
      warning_message: null,
    };

    render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={emptyPreview}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
      />,
    );

    expect(screen.getByText('/home/user/empty-skills')).toBeInTheDocument();
    expect(screen.getByText('未发现有效技能')).toBeInTheDocument();

    const adoptBtn = screen.getByRole('button', { name: '确认采纳并保存路径' });
    expect(adoptBtn).toBeDisabled();
  });

  it('renders skill cards, conflicts, tools, and triggers adoption callback', () => {
    const previewWithSkills: LocalSkillPathPreviewResponse = {
      resolved_path: '/Users/developer/custom-skills',
      exists: true,
      is_directory: true,
      total_discovered: 2,
      skills: [
        {
          name: 'super-search',
          description: 'A deep web search skill',
          version: '1.5.0',
          category: 'search',
          tags: ['web', 'ai'],
          required_tools: ['curl', 'jq'],
          relative_path: 'super-search',
          skill_id: 'local::supersearch12345',
          is_conflicted: true,
          conflict_reason: "Conflicts with existing prebuilt skill 'super-search'",
          is_safe: false,
          threat_summary: 'Potential command injection risk detected',
        },
        {
          name: 'markdown-formatter',
          description: 'Cleans up markdown formatting',
          version: '2.0.0',
          category: 'text',
          tags: ['markdown'],
          required_tools: [],
          relative_path: 'markdown-formatter',
          skill_id: 'local::markdown67890',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: true,
          threat_summary: null,
        },
      ],
      warning_message: 'Sample test warning',
    };

    render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={previewWithSkills}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
      />,
    );

    expect(screen.getByText('/Users/developer/custom-skills')).toBeInTheDocument();
    expect(screen.getByText('Sample test warning')).toBeInTheDocument();

    // Verify Skill 1 details
    expect(screen.getAllByText('super-search').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('v1.5.0')).toBeInTheDocument();
    expect(screen.getByText('search')).toBeInTheDocument();
    expect(screen.getByText('同名冲突')).toBeInTheDocument();
    expect(screen.getByText("Conflicts with existing prebuilt skill 'super-search'")).toBeInTheDocument();
    expect(screen.getByText('潜在安全风险')).toBeInTheDocument();
    expect(screen.getByText('curl')).toBeInTheDocument();
    expect(screen.getByText('jq')).toBeInTheDocument();

    // Verify Skill 2 details
    expect(screen.getAllByText('markdown-formatter').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('v2.0.0')).toBeInTheDocument();
    expect(screen.getByText('安全无风险')).toBeInTheDocument();

    // Verify Adopt Action
    const adoptBtn = screen.getByRole('button', { name: '确认采纳并保存路径' });
    expect(adoptBtn).not.toBeDisabled();
    fireEvent.click(adoptBtn);
    expect(onConfirmAdopt).toHaveBeenCalledTimes(1);
    // Non-conflicted valid skill is selected by default
    expect(onConfirmAdopt).toHaveBeenCalledWith(['local::markdown67890']);

    // Verify Cancel Action
    const cancelBtn = screen.getByRole('button', { name: '取消' });
    fireEvent.click(cancelBtn);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('supports select all, deselect all, and add path only actions', () => {
    const onAddPathOnly = vi.fn();
    const previewWithSkills: LocalSkillPathPreviewResponse = {
      resolved_path: '/Users/developer/test-skills',
      exists: true,
      is_directory: true,
      total_discovered: 2,
      skills: [
        {
          name: 'skill-one',
          description: 'First skill',
          version: '1.0.0',
          category: 'tool',
          tags: [],
          required_tools: [],
          relative_path: 'skill-one',
          skill_id: 'local::one111',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: true,
          threat_summary: null,
        },
        {
          name: 'skill-two',
          description: 'Second skill',
          version: '1.0.0',
          category: 'tool',
          tags: [],
          required_tools: [],
          relative_path: 'skill-two',
          skill_id: 'local::two222',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: true,
          threat_summary: null,
        },
      ],
      warning_message: null,
    };

    render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={previewWithSkills}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
        onAddPathOnly={onAddPathOnly}
      />,
    );

    // Initial state: both selected
    const deselectBtn = screen.getByTestId('preview-deselect-all-btn');
    fireEvent.click(deselectBtn);

    // After deselect all, adopt button should be disabled
    const adoptBtn = screen.getByTestId('preview-adopt-btn');
    expect(adoptBtn).toBeDisabled();

    // Select all
    const selectAllBtn = screen.getByTestId('preview-select-all-btn');
    fireEvent.click(selectAllBtn);
    expect(adoptBtn).not.toBeDisabled();

    // Add path only button
    const addPathOnlyBtn = screen.getByTestId('preview-add-path-only-btn');
    fireEvent.click(addPathOnlyBtn);
    expect(onAddPathOnly).toHaveBeenCalledTimes(1);
  });
});

