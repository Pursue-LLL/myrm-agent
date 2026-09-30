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
  'previewDialog.securityScore': '安全分',
  'previewDialog.securityBlocked': '门禁阻断',
  'previewDialog.securityBlockedTooltip': '安全评分低于 50 分，已触发自动化合规门禁阻断，不可直接采纳',
  'previewDialog.showFindings': '展开风险明细',
  'previewDialog.hideFindings': '收起风险明细',
  'previewDialog.line': '第 {line} 行',
  'previewDialog.threatLevel': '等级',
  'previewDialog.allowUntrustedDescription': '已知晓安全风险，允许受控采纳未受信任技能',
  'previewDialog.adoptWithRisk': '包含风险技能并采纳',
};

const stableT = (key: string, params?: Record<string, unknown>) => {
  let val = mockTranslations[key] ?? key;
  if (params?.count !== undefined) {
    val = `${val} (${params.count})`;
  }
  if (params?.score !== undefined) {
    val = `${val} ${params.score}`;
  }
  if (params?.line !== undefined) {
    val = val.replace('{line}', String(params.line));
  }
  return val;
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
          author: null,
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
          security_score: 40,
        },
        {
          name: 'markdown-formatter',
          description: 'Cleans up markdown formatting',
          author: null,
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
          security_score: 95,
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

    // Verify Skill 1 (Blocked: score 40 < 50)
    expect(screen.getAllByText('super-search').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('v1.5.0')).toBeInTheDocument();
    expect(screen.getByText('search')).toBeInTheDocument();
    expect(screen.getByText('同名冲突')).toBeInTheDocument();
    expect(screen.getByText("Conflicts with existing prebuilt skill 'super-search'")).toBeInTheDocument();
    expect(screen.getByTestId('security-score-badge-blocked')).toBeInTheDocument();
    expect(screen.getByTestId('security-blocked-notice')).toBeInTheDocument();
    expect(screen.getByText('curl')).toBeInTheDocument();
    expect(screen.getByText('jq')).toBeInTheDocument();

    // Checkbox for blocked skill should be disabled
    const blockedCheckbox = screen.getByTestId('preview-skill-checkbox-super-search');
    expect(blockedCheckbox).toBeDisabled();

    // Verify Skill 2 (Safe: score 95)
    expect(screen.getAllByText('markdown-formatter').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('v2.0.0')).toBeInTheDocument();
    expect(screen.getByTestId('security-score-badge-safe')).toBeInTheDocument();

    // Verify Adopt Action: only markdown-formatter should be adopted
    const adoptBtn = screen.getByRole('button', { name: '确认采纳并保存路径' });
    expect(adoptBtn).not.toBeDisabled();
    fireEvent.click(adoptBtn);
    expect(onConfirmAdopt).toHaveBeenCalledTimes(1);
    expect(onConfirmAdopt).toHaveBeenCalledWith(['local::markdown67890']);

    // Verify Cancel Action
    const cancelBtn = screen.getByRole('button', { name: '取消' });
    fireEvent.click(cancelBtn);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('supports select all (excluding blocked skills), deselect all, and add path only actions', () => {
    const onAddPathOnly = vi.fn();
    const previewWithSkills: LocalSkillPathPreviewResponse = {
      resolved_path: '/Users/developer/test-skills',
      exists: true,
      is_directory: true,
      total_discovered: 3,
      skills: [
        {
          name: 'skill-safe',
          description: 'Safe skill',
          author: null,
          version: '1.0.0',
          category: 'tool',
          tags: [],
          required_tools: [],
          relative_path: 'skill-safe',
          skill_id: 'local::safe111',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: true,
          threat_summary: null,
          security_score: 90,
        },
        {
          name: 'skill-warn',
          description: 'Moderate risk skill',
          author: null,
          version: '1.0.0',
          category: 'tool',
          tags: [],
          required_tools: [],
          relative_path: 'skill-warn',
          skill_id: 'local::warn222',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: false,
          threat_summary: 'Minor warning',
          security_score: 65,
        },
        {
          name: 'skill-blocked',
          description: 'Dangerous skill blocked by gate',
          author: null,
          version: '1.0.0',
          category: 'tool',
          tags: [],
          required_tools: [],
          relative_path: 'skill-blocked',
          skill_id: 'local::blocked333',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: false,
          threat_summary: 'Critical vulnerability',
          security_score: 30,
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

    // Initial state: safe and warn selected, blocked excluded
    const adoptBtn = screen.getByTestId('preview-adopt-confirm-btn');
    expect(adoptBtn).not.toBeDisabled();

    // Deselect all
    const toggleBtn = screen.getByTestId('preview-toggle-selection-btn');
    fireEvent.click(toggleBtn);
    expect(adoptBtn).toBeDisabled();

    // Select all (should only select safe and warn, never blocked)
    fireEvent.click(toggleBtn);
    expect(adoptBtn).not.toBeDisabled();

    fireEvent.click(adoptBtn);
    expect(onConfirmAdopt).toHaveBeenCalledWith(['local::safe111', 'local::warn222']);

    // Add path only button
    const addPathOnlyBtn = screen.getByTestId('preview-adopt-add-path-only-btn');
    fireEvent.click(addPathOnlyBtn);
    expect(onAddPathOnly).toHaveBeenCalledTimes(1);
  });

  it('renders findings details drawer and toggles expansion correctly', () => {
    const previewWithFindings: LocalSkillPathPreviewResponse = {
      resolved_path: '/Users/developer/findings-skills',
      exists: true,
      is_directory: true,
      total_discovered: 1,
      skills: [
        {
          name: 'audited-skill',
          description: 'Skill with audit findings',
          author: null,
          version: '1.0.0',
          category: 'ops',
          tags: [],
          required_tools: [],
          relative_path: 'audited-skill',
          skill_id: 'local::audit123',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: false,
          threat_summary: 'Found sensitive patterns',
          security_score: 45,
          security: {
            score: 45,
            trust_recommendation: 'blocked',
            total_findings: 2,
            finding_counts: { command_injection: 1, hardcoded_secret: 1 },
            findings: [
              {
                threat_type: 'command_injection',
                severity: 'critical',
                description: 'Detected raw shell execution via os.system',
                line_number: 28,
              },
              {
                threat_type: 'hardcoded_secret',
                severity: 'high',
                description: 'Exposed API token pattern in config',
                line_number: 42,
              },
            ],
          },
        },
      ],
      warning_message: null,
    };

    render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={previewWithFindings}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
      />,
    );

    // Toggle button should be visible
    const toggleFindingsBtn = screen.getByTestId('toggle-findings-btn');
    expect(toggleFindingsBtn).toBeInTheDocument();
    expect(screen.queryByTestId('findings-inspection-panel')).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(toggleFindingsBtn);
    expect(screen.getByTestId('findings-inspection-panel')).toBeInTheDocument();
    expect(screen.getByText('command_injection')).toBeInTheDocument();
    expect(screen.getByText('Detected raw shell execution via os.system')).toBeInTheDocument();
    expect(screen.getByText('第 28 行')).toBeInTheDocument();
    expect(screen.getByText('hardcoded_secret')).toBeInTheDocument();
    expect(screen.getByText('第 42 行')).toBeInTheDocument();

    // Click to hide
    fireEvent.click(toggleFindingsBtn);
    expect(screen.queryByTestId('findings-inspection-panel')).not.toBeInTheDocument();
  });

  it('supports controlled override for blocked skills and passes allowUntrusted to onConfirmAdopt', () => {
    const previewWithBlocked: LocalSkillPathPreviewResponse = {
      resolved_path: '/home/user/admin-skills',
      exists: true,
      is_directory: true,
      total_discovered: 1,
      skills: [
        {
          name: 'k8s-pod-restart',
          description: 'Restarts pods in a Kubernetes cluster',
          author: null,
          category: 'ops',
          tags: ['k8s'],
          version: '1.0.0',
          skill_id: 'local::k8s-pod-restart',
          relative_path: 'k8s-pod-restart/SKILL.md',
          is_conflicted: false,
          conflict_reason: null,
          is_safe: false,
          threat_summary: 'Detected system command execution',
          security_score: 45,
          security: {
            score: 45,
            trust_recommendation: 'review_before_adopt',
            finding_counts: { command_injection: 1 },
            total_findings: 1,
            findings: [],
          },
          required_tools: [],
        },
      ],
      warning_message: null,
    };

    render(
      <LocalSkillPathScanPreviewBeforeAdoptDialog
        open={true}
        onOpenChange={onOpenChange}
        previewData={previewWithBlocked}
        isAdopting={false}
        onConfirmAdopt={onConfirmAdopt}
      />,
    );

    // Controlled override warning banner should be rendered
    expect(screen.getByTestId('allow-untrusted-warning-banner')).toBeInTheDocument();
    const checkbox = screen.getByTestId('preview-skill-checkbox-k8s-pod-restart');
    // Initially disabled because score < 50
    expect(checkbox).toBeDisabled();

    // Toggle allow-untrusted override
    const allowUntrustedCheckbox = screen.getByTestId('allow-untrusted-skills-checkbox');
    expect(allowUntrustedCheckbox).not.toBeChecked();
    fireEvent.click(allowUntrustedCheckbox);
    expect(allowUntrustedCheckbox).toBeChecked();

    // Now the skill checkbox should become enabled
    expect(checkbox).not.toBeDisabled();
    fireEvent.click(checkbox);

    // Click confirm adopt button which now dynamically reflects risk warning
    const adoptBtn = screen.getByTestId('preview-adopt-confirm-btn');
    expect(adoptBtn).not.toBeDisabled();
    expect(adoptBtn).toHaveTextContent('包含风险技能并采纳');
    fireEvent.click(adoptBtn);

    expect(onConfirmAdopt).toHaveBeenCalledWith(['local::k8s-pod-restart'], true);
  });
});
