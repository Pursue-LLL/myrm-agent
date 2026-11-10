/**
 * The action space estimate of the edit dialog.
 *
 * Real scenario: while the user adjusts skills, MCP servers or built-in tools, the dialog asks the server how crowded
 * the action space of the draft is and shows the answer on the radar. A slow or failing server must neither leave the
 * radar spinning nor let an old answer overwrite a newer one, and a dialog that is closed (or shows no estimate)
 * asks for nothing. Pruning the stale core skills is in AgentConfigEditDialog.prune.test.tsx.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import type { ConfigCardType } from '../AgentConfigCards';
import { dialogProps, kit, resetKit, skillsPanel, type DialogProps } from './editDialogKit';
import {
  bodyOf,
  completePreview,
  estimate,
  fetchMock,
  installFakeServer,
  json,
  requests,
  watched,
} from './editDialogRequests';

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

const ESTIMATE = '/user-agents/evaluate-action-space';
const radar = () => screen.getByTestId('radar');

function show(type: ConfigCardType, overrides: Partial<DialogProps> = {}) {
  return render(<AgentConfigEditDialog {...dialogProps(type, overrides)} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  resetKit();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  installFakeServer();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AgentConfigEditDialog: action space estimate', () => {
  it('estimates the draft once the user stops changing it, and shows the answer', async () => {
    fetchMock.mockImplementation(async () => estimate());
    show('skills', { skillConfigs: { s1: { is_core: true } } });
    expect(radar()).toHaveAttribute('data-evaluating', 'true');

    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

    expect(radar()).toHaveAttribute('data-evaluating', 'false');
    expect(radar()).toHaveAttribute('data-high', 'true');
    expect(radar()).toHaveAttribute('data-critical', 'false');
    expect(skillsPanel().noiseData).toEqual({
      isNoiseHigh: true,
      isNoiseCritical: false,
      noiseLevel: 75,
      actionSpaceScore: 900,
      maxSafeScore: 1200,
    });
    expect(JSON.parse(radar().getAttribute('data-preview') ?? 'null')).toEqual(completePreview);
    expect(requests(ESTIMATE)).toHaveLength(1);
    expect(bodyOf(requests(ESTIMATE)[0])).toEqual({
      skill_ids: ['s1'],
      skill_configs: { s1: { is_core: true } },
      mcp_servers: ['docs'],
      enabled_builtin_tools: ['web_search'],
    });
  });

  it('waits until the user has paused for half a second before asking', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(async () => estimate());
    show('skills');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(requests(ESTIMATE)).toHaveLength(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(requests(ESTIMATE)).toHaveLength(1);
  });

  it('sends one request for a burst of changes, carrying the last draft', async () => {
    fetchMock.mockImplementation(async () => estimate());
    show('skills');

    act(() => skillsPanel().setLocalSkillIds(['s1', 's2']));
    act(() => skillsPanel().setLocalSkillIds(['s2']));

    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));
    const calls = requests(ESTIMATE);
    expect(calls).toHaveLength(1);
    expect(bodyOf(calls[0])).toMatchObject({ skill_ids: ['s2'] });
  });

  it('estimates the tools the draft will really save, without those the plan lacks', async () => {
    kit.sandbox = true;
    kit.entitlements = { canUseCron: false, canUseVnc: true, isLoading: false };
    fetchMock.mockImplementation(async () => estimate());
    show('builtin_tools', { enabledBuiltinTools: ['web_search', 'cron', 'computer_use'] });

    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(1));

    expect(bodyOf(requests(ESTIMATE)[0])).toMatchObject({ enabled_builtin_tools: ['web_search', 'computer_use'] });
  });

  it('never shows the noise above 100 percent', async () => {
    fetchMock.mockImplementation(async () => estimate({ ascs_score: 3000 }));
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

    expect(skillsPanel().noiseData.noiseLevel).toBe(100);
  });

  it.each(Object.keys(completePreview))(
    'shows no catalog preview when the server leaves out %s, rather than half of one',
    async (field) => {
      const incomplete = Object.fromEntries(Object.entries(completePreview).filter(([key]) => key !== field));
      fetchMock.mockImplementation(async () => estimate({ catalog_preview: incomplete }));
      show('skills');

      await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

      expect(radar()).toHaveAttribute('data-preview', 'null');
    },
  );

  it.each([
    ['nothing', null],
    ['text', 'inline'],
    ['a number', 3],
    ['a flag that is not a boolean', { ...completePreview, search_mounted: 'yes' }],
  ])('shows no catalog preview when the server sends %s', async (_name, preview) => {
    fetchMock.mockImplementation(async () => estimate({ catalog_preview: preview }));
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

    expect(radar()).toHaveAttribute('data-preview', 'null');
    expect(console.error).not.toHaveBeenCalled();
  });

  it('keeps the previous estimate when the answer carries none', async () => {
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-evaluating', 'false'));

    expect(radar()).toHaveAttribute('data-level', '100');
    expect(console.error).not.toHaveBeenCalled();
  });

  it.each([
    ['refuses', async () => json({ detail: 'nope' }, 500)],
    ['cannot be reached', async () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('keeps the previous estimate and stops evaluating when the server %s', async (_name, respond) => {
    fetchMock.mockImplementation(respond);
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-evaluating', 'false'));

    expect(radar()).toHaveAttribute('data-level', '100');
  });

  it('lets the newer answer stand when an older request is answered after it', async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    const older = watched(estimate({ accuracy_level: 20 }));
    const answers = [first, second];
    let asked = 0;
    fetchMock.mockImplementation((url) =>
      url.includes(ESTIMATE) ? answers[asked++].promise : Promise.resolve(json({})),
    );
    show('skills');
    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(1));

    act(() => skillsPanel().setLocalSkillIds(['s2']));
    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(2));
    expect(requests(ESTIMATE)[0][1]?.signal?.aborted).toBe(true);
    expect(requests(ESTIMATE)[1][1]?.signal?.aborted).toBe(false);
    await act(async () => {
      second.resolve(estimate({ accuracy_level: 90 }));
      await second.promise;
    });
    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '90'));

    await act(async () => {
      first.resolve(older.response);
      await older.settled();
    });

    expect(radar()).toHaveAttribute('data-level', '90');
    expect(radar()).toHaveAttribute('data-evaluating', 'false');
  });

  it('keeps evaluating when the draft goes back to one whose old request was overtaken', async () => {
    const first = deferred<Response>();
    const older = watched(estimate({ accuracy_level: 20 }));
    const answers = [first, deferred<Response>(), deferred<Response>()];
    let asked = 0;
    fetchMock.mockImplementation((url) =>
      url.includes(ESTIMATE) ? answers[asked++].promise : Promise.resolve(json({})),
    );
    show('skills');
    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(1));
    act(() => skillsPanel().setLocalSkillIds(['s2']));
    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(2));
    await act(async () => {
      first.resolve(older.response);
      await older.settled();
    });

    act(() => skillsPanel().setLocalSkillIds(['s1']));

    expect(radar()).toHaveAttribute('data-evaluating', 'true');
    expect(radar()).toHaveAttribute('data-level', '100');
  });

  it('shows it is evaluating again as soon as the draft changes after an answer', async () => {
    fetchMock.mockImplementation(async () => estimate());
    show('skills');
    await waitFor(() => expect(radar()).toHaveAttribute('data-evaluating', 'false'));

    act(() => skillsPanel().setLocalSkillIds(['s2']));

    expect(radar()).toHaveAttribute('data-evaluating', 'true');
    await waitFor(() => expect(radar()).toHaveAttribute('data-evaluating', 'false'));
  });

  it('treats an error page of the server as a refusal, without noise', async () => {
    fetchMock.mockImplementation(async () => new Response('<html>Bad gateway</html>', { status: 502 }));
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-evaluating', 'false'));

    expect(radar()).toHaveAttribute('data-level', '100');
    expect(console.error).not.toHaveBeenCalled();
  });

  it.each([
    [905, 75],
    [910, 76],
  ])('rounds the noise of a score of %i to %i percent', async (score, percent) => {
    fetchMock.mockImplementation(async () => estimate({ ascs_score: score }));
    show('skills');

    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

    expect(skillsPanel().noiseData.noiseLevel).toBe(percent);
  });

  it('stays quiet about a request it cancelled itself', async () => {
    let asked = 0;
    fetchMock.mockImplementation((url, init) => {
      if (!url.includes(ESTIMATE)) {
        return Promise.resolve(json({}));
      }
      asked += 1;
      if (asked > 1) {
        return Promise.resolve(estimate());
      }
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
    });
    show('skills');
    await waitFor(() => expect(requests(ESTIMATE)).toHaveLength(1));

    act(() => skillsPanel().setLocalSkillIds(['s2']));
    await waitFor(() => expect(radar()).toHaveAttribute('data-level', '64'));

    expect(console.error).not.toHaveBeenCalled();
  });

  it('asks for nothing while the dialog is closed or on the instruction card, which shows no estimate', () => {
    vi.useFakeTimers();
    show('skills', { open: false });
    show('instruction');

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(requests(ESTIMATE)).toHaveLength(0);
  });
});
