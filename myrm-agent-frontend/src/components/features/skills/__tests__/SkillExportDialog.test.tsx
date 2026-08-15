/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SkillExportDialog from '../SkillExportDialog';
import type { Skill } from '@/store/skill/types';

const toastMock = vi.hoisted(() => vi.fn());
const previewSkillPackageMock = vi.hoisted(() => vi.fn());
const downloadSkillMock = vi.hoisted(() => vi.fn());
const triggerDownloadMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  'title': 'Export {name}',
  'description': 'description',
  'scanning': 'scanning',
  'safeTitle': 'safeTitle',
  'safeDescription': 'safeDescription',
  'warningTitle': 'warningTitle',
  'warningDescription': 'warningDescription',
  'evalCasesIncluded': '({count} eval cases)',
  'diffPreview': 'diffPreview',
  'toggleAll': 'toggleAll',
  'cancel': 'cancel',
  'exportOriginal': 'exportOriginal',
  'exportRedacted': 'exportRedacted',
  'export': 'export',
  'previewFailed': 'previewFailed',
  'exportSuccess': 'exportSuccess',
  'exportFailed': 'exportFailed',
};

const stableT = (key: string, values?: Record<string, string | number>): string => {
  let text = TRANSLATIONS[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

vi.mock('@/services/skill', () => ({
  previewSkillPackage: previewSkillPackageMock,
  downloadSkill: downloadSkillMock,
}));

vi.mock('@/lib/utils/fileUtils', () => ({
  triggerDownload: triggerDownloadMock,
}));

function makeSkill(overrides: Partial<Skill> = {}): Skill {
  return {
    id: 'skill-1',
    name: 'demo-skill',
    version: '1.0.0',
    ...overrides,
  } as Skill;
}

describe('SkillExportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows eval cases count in safe alert when eval_cases_count > 0', async () => {
    previewSkillPackageMock.mockResolvedValue({
      success: true,
      is_safe: true,
      error: null,
      redactions: null,
      eval_cases_count: 3,
    });

    render(<SkillExportDialog skill={makeSkill()} open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/safeDescription/)).toBeInTheDocument();
    });
    expect(screen.getByText(/3 eval cases/)).toBeInTheDocument();
  });

  it('omits eval cases message when eval_cases_count is 0', async () => {
    previewSkillPackageMock.mockResolvedValue({
      success: true,
      is_safe: true,
      error: null,
      redactions: null,
      eval_cases_count: 0,
    });

    render(<SkillExportDialog skill={makeSkill()} open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/safeDescription/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/eval cases/)).not.toBeInTheDocument();
  });

  it('uses backend-provided filename for download', async () => {
    previewSkillPackageMock.mockResolvedValue({
      success: true,
      is_safe: true,
      error: null,
      redactions: null,
      eval_cases_count: 0,
    });
    downloadSkillMock.mockResolvedValue({
      blob: new Blob(['zip']),
      filename: 'demo-skill_v7.zip',
    });

    render(<SkillExportDialog skill={makeSkill()} open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^export$/ })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /^export$/ }));

    await waitFor(() => {
      expect(downloadSkillMock).toHaveBeenCalledWith('skill-1', true, {});
    });
    await waitFor(() => {
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'demo-skill_v7.zip');
    });
  });

  it('falls back to local filename when backend omits it', async () => {
    previewSkillPackageMock.mockResolvedValue({
      success: true,
      is_safe: true,
      error: null,
      redactions: null,
      eval_cases_count: 0,
    });
    downloadSkillMock.mockResolvedValue({ blob: new Blob(['zip']), filename: null });

    render(<SkillExportDialog skill={makeSkill()} open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^export$/ })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /^export$/ }));

    await waitFor(() => {
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'demo-skill_v1.0.0.zip');
    });
  });

  it('shows warning alert with eval cases count when not safe', async () => {
    previewSkillPackageMock.mockResolvedValue({
      success: true,
      is_safe: false,
      error: null,
      redactions: {
        'SKILL.md': [
          {
            line_number: 3,
            original: 'api_key=sk-secret',
            redacted: 'api_key=<REDACTED>',
            reason: 'API key',
          },
        ],
      },
      eval_cases_count: 2,
    });

    render(<SkillExportDialog skill={makeSkill()} open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/warningDescription/)).toBeInTheDocument();
    });
    expect(screen.getByText(/2 eval cases/)).toBeInTheDocument();
  });
});
