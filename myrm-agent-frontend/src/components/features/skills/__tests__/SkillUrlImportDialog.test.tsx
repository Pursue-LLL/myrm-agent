import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SkillUrlImportDialog from '../SkillUrlImportDialog';

const mockAnalyzeDiscoveryUrl = vi.fn();
const mockInstallDiscoverySkillFromUrl = vi.fn();
let mockIsLocalModeValue = true;

vi.mock('@/services/skill', () => ({
  analyzeDiscoveryUrl: (...args: unknown[]) => mockAnalyzeDiscoveryUrl(...args),
  installDiscoverySkillFromUrl: (...args: unknown[]) => mockInstallDiscoverySkillFromUrl(...args),
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => mockIsLocalModeValue,
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { agentConfig: { agentId: string } }) => unknown) =>
    selector({ agentConfig: { agentId: 'test-agent' } }),
}));

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    importUrl: 'Import GitHub URL',
    importUrlPlaceholder: 'Paste GitHub repo or deep link...',
    securityDisclosureTitle: 'Security & Sandbox Boundary Disclosure',
    securityDisclosureLocal:
      'Currently running in local/desktop mode. The agent executes tools with your host operating system permissions.',
    securityDisclosureCloud: 'Currently running in an isolated microVM container with persistent volume isolation.',
    trustedSourceConfirm:
      'I understand this extension has system tool execution permissions and confirm this source is trusted',
    analyzingUrl: 'Analyzing...',
    analyzeFailed: 'Failed to analyze URL',
    selectSkillsToImport: 'Discovered skills:',
    importSelected: 'Import Selected',
    import: 'Import',
    cancel: 'Cancel',
    alreadyInstalled: 'Already Installed',
    installing: 'Installing...',
    installed: 'Installed successfully!',
    installFailed: 'Install failed',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SkillUrlImportDialog Security & Trusted Source Gates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLocalModeValue = true;
  });

  it('renders initial state without security disclosure card before analysis', () => {
    render(<SkillUrlImportDialog open={true} onOpenChange={vi.fn()} />);

    expect(screen.getByTestId('skill-url-input')).toBeInTheDocument();
    expect(screen.getByTestId('analyze-url-btn')).toBeDisabled();
    expect(screen.queryByTestId('security-disclosure-card')).not.toBeInTheDocument();
    expect(screen.queryByTestId('trusted-source-checkbox')).not.toBeInTheDocument();
  });

  it('single URL analysis renders skill item and disclosure card without silent auto-install', async () => {
    mockAnalyzeDiscoveryUrl.mockResolvedValueOnce({
      urls: [
        {
          url: 'https://github.com/trusted-org/financial-skill',
          name: 'FinancialSkill',
          description: 'Analyzes quarterly reports',
          is_installed: false,
        },
      ],
    });

    render(<SkillUrlImportDialog open={true} onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByTestId('skill-url-input'), {
      target: { value: 'https://github.com/trusted-org/financial-skill' },
    });

    expect(screen.getByTestId('analyze-url-btn')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('analyze-url-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('security-disclosure-card')).toBeInTheDocument();
    });

    // CRITICAL: verify silent auto-install did NOT happen
    expect(mockInstallDiscoverySkillFromUrl).not.toHaveBeenCalled();

    // Verify skill item and local security disclosure text
    expect(screen.getByText('FinancialSkill')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Currently running in local\/desktop mode\. The agent executes tools with your host operating system permissions\./i,
      ),
    ).toBeInTheDocument();

    // Verify import button is disabled because trusted source is not checked
    const importBtn = screen.getByTestId('import-skills-btn');
    expect(importBtn).toBeDisabled();
  });

  it('enables import button only after checking trusted source and executes install', async () => {
    mockAnalyzeDiscoveryUrl.mockResolvedValueOnce({
      urls: [
        {
          url: 'https://github.com/trusted-org/financial-skill',
          name: 'FinancialSkill',
          description: 'Analyzes quarterly reports',
          is_installed: false,
        },
      ],
    });
    mockInstallDiscoverySkillFromUrl.mockResolvedValueOnce({ success: true });
    const onOpenChange = vi.fn();
    const onInstalled = vi.fn();

    render(<SkillUrlImportDialog open={true} onOpenChange={onOpenChange} onInstalled={onInstalled} />);

    fireEvent.change(screen.getByTestId('skill-url-input'), {
      target: { value: 'https://github.com/trusted-org/financial-skill' },
    });
    fireEvent.click(screen.getByTestId('analyze-url-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('security-disclosure-card')).toBeInTheDocument();
    });

    const checkbox = screen.getByTestId('trusted-source-checkbox');
    const importBtn = screen.getByTestId('import-skills-btn');
    expect(importBtn).toBeDisabled();

    // Check trusted source
    fireEvent.click(checkbox);
    expect(importBtn).not.toBeDisabled();

    // Click import
    fireEvent.click(importBtn);

    await waitFor(() => {
      expect(mockInstallDiscoverySkillFromUrl).toHaveBeenCalledWith('https://github.com/trusted-org/financial-skill', {
        agentId: 'test-agent',
        mountToAgent: true,
      });
    });

    await waitFor(() => {
      expect(onInstalled).toHaveBeenCalledTimes(1);
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('renders cloud sandbox security disclosure when isLocalMode is false', async () => {
    mockIsLocalModeValue = false;
    mockAnalyzeDiscoveryUrl.mockResolvedValueOnce({
      urls: [
        {
          url: 'https://github.com/org/cloud-extension',
          name: 'CloudExtension',
          is_installed: false,
        },
      ],
    });

    render(<SkillUrlImportDialog open={true} onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByTestId('skill-url-input'), {
      target: { value: 'https://github.com/org/cloud-extension' },
    });
    fireEvent.click(screen.getByTestId('analyze-url-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('security-disclosure-card')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Currently running in an isolated microVM container with persistent volume isolation\./i),
    ).toBeInTheDocument();
  });

  it('handles multi-skill analysis and selection toggling with trusted source gate', async () => {
    mockAnalyzeDiscoveryUrl.mockResolvedValueOnce({
      urls: [
        {
          url: 'https://github.com/org/multi-skills#skill1',
          name: 'SkillOne',
          description: 'First skill',
          is_installed: false,
        },
        {
          url: 'https://github.com/org/multi-skills#skill2',
          name: 'SkillTwo',
          description: 'Second skill',
          is_installed: false,
        },
      ],
    });
    mockInstallDiscoverySkillFromUrl.mockResolvedValue({ success: true });
    const onInstalled = vi.fn();

    render(<SkillUrlImportDialog open={true} onOpenChange={vi.fn()} onInstalled={onInstalled} />);

    fireEvent.change(screen.getByTestId('skill-url-input'), {
      target: { value: 'https://github.com/org/multi-skills' },
    });
    fireEvent.click(screen.getByTestId('analyze-url-btn'));

    await waitFor(() => {
      expect(screen.getByText('SkillOne')).toBeInTheDocument();
      expect(screen.getByText('SkillTwo')).toBeInTheDocument();
    });

    const checkbox = screen.getByTestId('trusted-source-checkbox');
    const importBtn = screen.getByTestId('import-skills-btn');
    expect(importBtn).toBeDisabled();

    // Confirm trusted source
    fireEvent.click(checkbox);
    expect(importBtn).not.toBeDisabled();

    // Toggle off SkillTwo
    const skill2Checkbox = screen.getByRole('checkbox', { name: /skilltwo/i });
    fireEvent.click(skill2Checkbox);

    // Import only selected SkillOne
    fireEvent.click(importBtn);

    await waitFor(() => {
      expect(mockInstallDiscoverySkillFromUrl).toHaveBeenCalledTimes(1);
      expect(mockInstallDiscoverySkillFromUrl).toHaveBeenCalledWith('https://github.com/org/multi-skills#skill1', {
        agentId: 'test-agent',
        mountToAgent: true,
      });
    });
  });

  it('renders already installed badge and disables selection for installed skills', async () => {
    mockAnalyzeDiscoveryUrl.mockResolvedValueOnce({
      urls: [
        {
          url: 'https://github.com/org/installed-skill',
          name: 'InstalledSkill',
          description: 'Already installed',
          is_installed: true,
        },
      ],
    });

    render(<SkillUrlImportDialog open={true} onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByTestId('skill-url-input'), {
      target: { value: 'https://github.com/org/installed-skill' },
    });
    fireEvent.click(screen.getByTestId('analyze-url-btn'));

    await waitFor(() => {
      expect(screen.getByText('InstalledSkill')).toBeInTheDocument();
      expect(screen.getByText('Already Installed')).toBeInTheDocument();
    });

    // Checkbox for installed skill should be disabled
    const installedCheckbox = screen.getByRole('checkbox', { name: /installedskill/i });
    expect(installedCheckbox).toBeDisabled();

    // Import button should remain disabled because selectedUrls.size is 0
    const importBtn = screen.getByTestId('import-skills-btn');
    expect(importBtn).toBeDisabled();
  });
});
