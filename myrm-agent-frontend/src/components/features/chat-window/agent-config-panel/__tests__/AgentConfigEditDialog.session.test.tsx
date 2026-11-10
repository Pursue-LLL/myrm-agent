/**
 * The edit dialog while its closing animation is still on screen.
 *
 * Real scenario: the user cancels and clicks the card again before the dialog finished fading out. The old form is
 * still mounted at that moment, so it must be rebuilt from the current settings instead of showing the abandoned
 * draft. The dialog primitive is replaced by one that keeps its content mounted, which is what the animation does.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { dialogProps, kit, resetKit } from './editDialogKit';

vi.mock('@/components/primitives/dialog', () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    Dialog: Passthrough,
    DialogContent: Passthrough,
    DialogHeader: Passthrough,
    DialogTitle: Passthrough,
    DialogFooter: Passthrough,
  };
});
vi.mock('next/dynamic', async () => (await import('./editDialogKit')).nextDynamicMock());
vi.mock('@/hooks/billing/useFeatureEntitlements', async () => (await import('./editDialogKit')).entitlementsMock());
vi.mock('@/lib/deploy-mode', async (importOriginal) =>
  (await import('./editDialogKit')).deployModeMock(await importOriginal<typeof import('@/lib/deploy-mode')>()),
);
vi.mock('../ActionSpaceAccuracyRadar', async () => (await import('./editDialogKit')).radarMock());
vi.mock('../SkillsSectionPanel', async () => (await import('./editDialogKit')).skillsPanelMock());
vi.mock('../BuiltinToolsPanel', async () => (await import('./editDialogKit')).builtinToolsPanelMock());
vi.mock('../SubagentsPanel', async () => (await import('./editDialogKit')).subagentsPanelMock());
vi.mock('../InstructionPanel', async () => (await import('./editDialogKit')).instructionPanelMock());

import AgentConfigEditDialog from '../AgentConfigEditDialog';

beforeEach(() => {
  vi.resetAllMocks();
  resetKit();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ data: null }), { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AgentConfigEditDialog: closing animation', () => {
  const prompt = () => screen.getByTestId('instruction-panel').getAttribute('data-prompt');

  it('keeps the draft on screen while it closes, and rebuilds it from the current settings when opened again', () => {
    const view = render(<AgentConfigEditDialog {...dialogProps('instruction')} />);
    fireEvent.click(screen.getByRole('button', { name: 'type-prompt' }));
    expect(prompt()).toBe('Answer in French');

    view.rerender(<AgentConfigEditDialog {...dialogProps('instruction', { open: false })} />);
    expect(prompt()).toBe('Answer in French');

    view.rerender(<AgentConfigEditDialog {...dialogProps('instruction', { open: true, systemPrompt: 'Be formal' })} />);
    expect(prompt()).toBe('Be formal');
    expect(kit.onSave).not.toHaveBeenCalled();
  });
});
