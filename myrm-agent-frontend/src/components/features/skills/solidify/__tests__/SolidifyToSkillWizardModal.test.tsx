/** @vitest-environment jsdom */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SolidifyToSkillWizardModal } from '../SolidifyToSkillWizardModal';
import { SolidifyService } from '../solidifyService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '固化为专属 Skill 向导',
    subtitle: '将打磨好的成果一键提取参数并生成 4 合 1 标准全包技能',
    stepParams: '1. 参数最小化提取',
    stepBundle: '2. 模板与资产预览',
    stepConfirm: '3. 固化完成',
    paramHelp: '参数最小化原则',
    nameLabel: '技能唯一标识 (Identifier)',
    displayTitleLabel: '显示名称',
    descriptionLabel: '技能能力描述',
    planHint: '在生成的技能指令中默认注入「先规划再执行」门禁',
    solidifyBtn: '一键固化并落盘',
    solidifying: '正在打包生成 4 合 1 技能包...',
    successTitle: '专属技能固化成功！',
    successDesc: '已成功写入本地技能库',
    openPreview: '在外部浏览器中检验效果',
    close: '完成',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SolidifyToSkillWizardModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <SolidifyToSkillWizardModal isOpen={false} onClose={vi.fn()} artifactContent="<html><body>test</body></html>" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('initializes and extracts dynamic parameters from artifact HTML', () => {
    const sampleHtml = `
      <!DOCTYPE html><html><head><title>天体引力波模拟课件</title></head>
      <body><h1>双黑洞并合辐射</h1><p>互动模拟内容</p></body></html>
    `;

    render(<SolidifyToSkillWizardModal isOpen={true} onClose={vi.fn()} artifactContent={sampleHtml} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('固化为专属 Skill 向导')).toBeInTheDocument();
    expect(screen.getByText('1. 参数最小化提取')).toBeInTheDocument();
    // Identified dynamic slots
    expect(screen.getByText('{{topic}}')).toBeInTheDocument();
  });

  it('supports stepping through wizard from params to bundle preview and completing solidification', async () => {
    const sampleHtml = '<div>Hello {{name}}!</div>';
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    vi.spyOn(SolidifyService, 'solidifySkill').mockResolvedValue({
      skillId: 'skill-alpha-123',
      name: 'interactive-greeting',
      displayTitle: '问候课件生成器',
      description: '生成动态交互问候',
      parameters: [
        {
          name: 'name',
          description: '受众姓名',
          defaultValue: '同学',
          placeholderPattern: '{{name}}',
          required: true,
        },
      ],
      bundleFiles: ['SKILL.md', 'assets/template.html', 'assets/example.html', 'references/design_guidelines.md'],
      previewUrl: '/api/v1/skills/solidify/preview/prev-999',
      createdAt: new Date().toISOString(),
    });

    render(
      <SolidifyToSkillWizardModal
        isOpen={true}
        onClose={handleClose}
        artifactContent={sampleHtml}
        onSolidifiedSuccess={handleSuccess}
      />,
    );

    // Step 1: Params step -> click Next
    const nextBtn = screen.getByRole('button', { name: /下一步/i });
    fireEvent.click(nextBtn);

    // Step 2: Bundle preview step
    expect(screen.getByText('四位一体标准全包目录结构')).toBeInTheDocument();
    expect(screen.getByText('SKILL.md')).toBeInTheDocument();
    expect(screen.getByText('assets/template.html')).toBeInTheDocument();

    // Click solidify
    const solidifyBtn = screen.getByRole('button', { name: /一键固化并落盘/i });
    fireEvent.click(solidifyBtn);

    // Step 3: Success step
    await waitFor(() => {
      expect(screen.getByText('专属技能固化成功！')).toBeInTheDocument();
    });

    expect(handleSuccess).toHaveBeenCalledTimes(1);
    expect(screen.getByText('skill-alpha-123')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /在外部浏览器中检验效果/i })).toBeInTheDocument();

    // Click Done to close
    const closeBtn = screen.getByRole('button', { name: /完成/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
