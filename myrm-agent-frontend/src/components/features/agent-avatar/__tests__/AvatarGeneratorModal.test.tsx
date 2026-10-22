/**
 * Unit tests for AvatarGeneratorModal component.
 *
 * [INPUT] AvatarGeneratorModal, avatarService
 * [OUTPUT] Full coverage for modal lifecycle, mode switching (Dice vs AI), AI generation, and save/lock actions.
 * [POS] src/components/features/agent-avatar/__tests__/AvatarGeneratorModal.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AvatarGeneratorModal } from '../AvatarGeneratorModal';
import { avatarService } from '../avatarService';
import type { AvatarMetadata } from '../avatarTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    modalTitle: 'Agent Avatar Studio & Dice Lock',
    close: 'Close',
    tabDice: 'Deterministic Dice Roll',
    tabAi: 'AI Generative Avatar',
    aiPromptLabel: 'Avatar Persona Prompt',
    aiPromptPlaceholder: 'Describe bot appearance or persona...',
    generating: 'Generating...',
    generateAiCta: 'Cast AI Avatar',
    cancel: 'Cancel',
    saveAndLock: 'Save & Lock Avatar',
    avatarLocked: 'Avatar is locked',
    rollDice: 'Randomize Avatar',
    locked: 'Locked',
    diceRoll: 'Randomize',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../avatarService', () => ({
  avatarService: {
    generateAiAvatar: vi.fn(),
    generateSvg: vi.fn(),
    setAgentAvatar: vi.fn(),
    getAgentAvatar: vi.fn(),
  },
}));

describe('AvatarGeneratorModal', () => {
  const initialMetadata: AvatarMetadata = {
    seed: 'initial-agent-bot',
    style: 'beam',
    backgroundColor: '#6366f1',
    isLocked: false,
    svgData: '<svg data-testid="initial-svg"></svg>',
    imageUrl: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    render(<AvatarGeneratorModal agentId="agent-123" isOpen={false} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.queryByTestId('avatar-generator-modal')).toBeNull();
  });

  it('renders studio modal and triggers onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(
      <AvatarGeneratorModal
        agentId="agent-123"
        isOpen={true}
        onClose={onClose}
        onSave={vi.fn()}
        initialMetadata={initialMetadata}
      />,
    );

    expect(screen.getByTestId('avatar-generator-modal')).toBeDefined();
    expect(screen.getByText('Agent Avatar Studio & Dice Lock')).toBeDefined();

    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('switches between Dice and AI tabs', () => {
    render(
      <AvatarGeneratorModal
        agentId="agent-123"
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        initialMetadata={initialMetadata}
      />,
    );

    // Initial is dice tab, no AI prompt input yet
    expect(screen.queryByPlaceholderText('Describe bot appearance or persona...')).toBeNull();

    // Click AI Tab
    const aiTabBtn = screen.getByText('AI Generative Avatar');
    fireEvent.click(aiTabBtn);

    expect(screen.getByPlaceholderText('Describe bot appearance or persona...')).toBeDefined();
    expect(screen.getByText('Cast AI Avatar')).toBeDefined();

    // Click back to Dice tab
    const diceTabBtn = screen.getByText('Deterministic Dice Roll');
    fireEvent.click(diceTabBtn);
    expect(screen.queryByPlaceholderText('Describe bot appearance or persona...')).toBeNull();
  });

  it('triggers AI avatar generation and updates image in preview', async () => {
    vi.mocked(avatarService.generateAiAvatar).mockResolvedValueOnce('https://example.com/generated-owl.png');

    render(
      <AvatarGeneratorModal
        agentId="agent-123"
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        initialMetadata={initialMetadata}
      />,
    );

    // Switch to AI tab
    fireEvent.click(screen.getByText('AI Generative Avatar'));

    const textarea = screen.getByPlaceholderText('Describe bot appearance or persona...');
    fireEvent.change(textarea, { target: { value: 'Futuristic neon owl with cyan visor' } });

    const generateBtn = screen.getByText('Cast AI Avatar');
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(avatarService.generateAiAvatar).toHaveBeenCalledWith({
        prompt: 'Futuristic neon owl with cyan visor',
        style: 'beam',
      });
    });

    // Check that generated image is rendered in preview
    await waitFor(() => {
      const img = screen.getByAltText('Agent Avatar');
      expect(img.getAttribute('src')).toBe('https://example.com/generated-owl.png');
    });
  });

  it('saves and locks metadata when clicking Save & Lock button', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(
      <AvatarGeneratorModal
        agentId="agent-123"
        isOpen={true}
        onClose={onClose}
        onSave={onSave}
        initialMetadata={initialMetadata}
      />,
    );

    const saveBtn = screen.getByText('Save & Lock Avatar');
    fireEvent.click(saveBtn);

    expect(onSave).toHaveBeenCalledTimes(1);
    const savedMeta = onSave.mock.calls[0][0] as AvatarMetadata;
    expect(savedMeta.isLocked).toBe(true);
    expect(savedMeta.seed).toBe(initialMetadata.seed);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
