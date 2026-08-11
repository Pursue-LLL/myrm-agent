/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SkillDetectionCard from '../SkillDetectionCard';
import type { Artifact } from '@/store/chat/types';

const toastMock = vi.hoisted(() => vi.fn());
const packageWorkspaceDirectoryMock = vi.hoisted(() => vi.fn());
const uploadSkillMock = vi.hoisted(() => vi.fn());
const triggerDownloadMock = vi.hoisted(() => vi.fn());
const fetchMarketSkillsMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  'skillDetected': 'skillDetected',
  'skillDetectedDesc': 'skillDetectedDesc',
  'packageSuccess': 'packageSuccess',
  'packageFailed': 'packageFailed',
  'registerSuccess': 'registerSuccess',
  'registerFailed': 'registerFailed',
  'packageAndDownload': 'packageAndDownload',
  'packageAndRegister': 'packageAndRegister',
  'registering': 'registering',
  'registered': 'registered',
  'packaging': 'packaging',
  'evalCasesRestored': '{count} evals restored',
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
  packageWorkspaceDirectory: packageWorkspaceDirectoryMock,
  uploadSkill: uploadSkillMock,
  triggerDownload: triggerDownloadMock,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => false,
}));

vi.mock('@/store/skill', () => ({
  useSkillStore: (selector: (state: object) => unknown) =>
    selector({
      fetchMarketSkills: fetchMarketSkillsMock,
      marketSkills: [],
      localSkills: [],
    } as object),
}));

vi.mock('@/store/useAuthStore', () => ({
  default: (selector: (state: object) => unknown) =>
    selector({ user: { id: 'user-1' } } as object),
}));

vi.mock('@/store/useChatStore', () => ({
  useShallow: (selector: (state: object) => unknown) => selector,
  default: (selector: (state: object) => unknown) =>
    selector({ agentConfig: { selectedSkillIds: [] } } as object),
}));

vi.mock('@/lib/utils/skillErrorMapper', () => ({
  getFriendlyErrorMessage: (msg: string) => msg,
}));

function makeSkillArtifact(): Artifact {
  return {
    id: 'file-1',
    filename: 'files/my-skill/SKILL.md',
    type: 'document' as const,
    content_type: 'text/markdown',
    size: 100,
    preview_url: '',
    download_url: '',
  };
}

describe('SkillDetectionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders null when no SKILL.md artifact', () => {
    const { container } = render(
      <SkillDetectionCard artifacts={[]} chatId="chat-1" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows restored eval cases in register success toast', async () => {
    packageWorkspaceDirectoryMock.mockResolvedValue(new Blob(['zip']));
    uploadSkillMock.mockResolvedValue({
      success: true,
      skill_id: 'skill-1',
      skill_name: 'my_skill',
      error: null,
      restored_eval_cases: 4,
    });

    render(<SkillDetectionCard artifacts={[makeSkillArtifact()]} chatId="chat-1" />);

    fireEvent.click(screen.getByRole('button', { name: /packageAndRegister/ }));

    await waitFor(() => {
      expect(uploadSkillMock).toHaveBeenCalledWith(expect.any(File), true);
    });
    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'registerSuccess',
        description: 'my_skill (4 evals restored)',
      });
    });
  });

  it('omits restored info when no eval cases', async () => {
    packageWorkspaceDirectoryMock.mockResolvedValue(new Blob(['zip']));
    uploadSkillMock.mockResolvedValue({
      success: true,
      skill_id: 'skill-2',
      skill_name: 'plain_skill',
      error: null,
      restored_eval_cases: 0,
    });

    render(<SkillDetectionCard artifacts={[makeSkillArtifact()]} chatId="chat-1" />);

    fireEvent.click(screen.getByRole('button', { name: /packageAndRegister/ }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'registerSuccess',
        description: 'plain_skill',
      });
    });
  });
});
