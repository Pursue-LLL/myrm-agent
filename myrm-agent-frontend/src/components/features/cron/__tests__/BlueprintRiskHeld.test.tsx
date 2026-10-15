// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Sparkles } from 'lucide-react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sonnerToast, riskToast } = vi.hoisted(() => ({
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/services/channels', () => ({ listChannelStatuses: vi.fn(async () => []) }));

import type { CronBlueprint } from '../cron-blueprints';
import BlueprintFillDialog from '../BlueprintFillDialog';
import BlueprintInlineFill from '../BlueprintInlineFill';

const blueprint: CronBlueprint = {
  id: 'custom_reminder',
  icon: Sparkles,
  titleKey: 'blueprint.customReminder',
  descKey: 'blueprint.customReminderDesc',
  promptKey: 'blueprint.customReminderPrompt',
  slots: [],
  title: { en: 'Reminder' },
  description: { en: 'Remind me' },
  buildSchedule: () => ({ kind: 'once', at: '2030-01-01T09:00:00Z' }),
};

const filledBlueprint = {
  name: 'Reminder',
  job_type: 'reminder',
  schedule: { kind: 'once', at: '2030-01-01T09:00:00Z' },
  prompt: 'Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0',
  session_target: 'main',
  required_capabilities: [],
  tools_allowed: [],
  deduplicate: false,
  skip_if_active: false,
};

/** The blueprint fill succeeds; creating the job gets `createReply`. */
function stubCronApi(createReply: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) =>
      String(url).endsWith('/cron/blueprints/fill')
        ? jsonResponse(200, filledBlueprint)
        : init?.method === 'POST'
          ? createReply()
          : jsonResponse(200, {}),
    ),
  );
}

const renderers = [
  ['the blueprint dialog', () => render(<BlueprintFillDialog blueprint={blueprint} open onOpenChange={vi.fn()} />)],
  [
    'the inline blueprint form',
    () => render(<BlueprintInlineFill blueprint={blueprint} onBack={vi.fn()} onCreated={vi.fn()} />),
  ],
] as const;

describe.each(renderers)('creating a job from %s whose prompt the server holds', (_name, mount) => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains the held prompt once and shows no failure toast of its own', async () => {
    stubCronApi(() => jsonResponse(400, riskHeldRefusalBody));
    mount();

    fireEvent.click(screen.getByRole('button', { name: 'createSubmit' }));

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
  });

  it('still reports any other failure with the server message', async () => {
    stubCronApi(() => jsonResponse(500, { detail: 'Scheduler is down' }));
    mount();

    fireEvent.click(screen.getByRole('button', { name: 'createSubmit' }));

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('Scheduler is down'));
  });
});
