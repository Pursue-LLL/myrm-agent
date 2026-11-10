/** @vitest-environment jsdom */
import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import {
  agentState,
  chatState,
  chooseRouteAgent,
  click,
  deferred,
  mocks,
  openInlinePad,
  openRouteMenu,
  renderFlowPad,
  resetFlowPadKit,
  routeTrigger,
  submitText,
  TEAM_TEMPLATE,
} from './flowPadTestKit';

const CARD = 'flowpad-inline-template-cloudq-team-template';
const FIRST_USE_CASE = 'flowpad-inline-template-usecase-cloudq-team-template-0';
const FUNNEL = { contextKey: 'flowpad:inline', templateKind: 'team' };

async function summonFrom(testId: string): Promise<void> {
  await openRouteMenu();
  await click(await screen.findByTestId(testId));
}

describe('FlowPadModal: expert templates and summon', () => {
  beforeEach(() => {
    resetFlowPadKit();
    openInlinePad();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('template list', () => {
    it('lists only team templates', async () => {
      renderFlowPad();
      await openRouteMenu();

      expect(await screen.findByTestId(CARD)).toBeInTheDocument();
      expect(screen.queryByTestId('flowpad-inline-template-solo-template')).not.toBeInTheDocument();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);
    });

    it('asks for the templates once while the first request is still in flight', async () => {
      const pending = deferred<Array<typeof TEAM_TEMPLATE>>();
      mocks.getTemplates.mockImplementationOnce(() => pending.promise);
      renderFlowPad();

      await openRouteMenu();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);
      await click(routeTrigger());
      await openRouteMenu();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);
      await act(async () => {
        pending.resolve([TEAM_TEMPLATE]);
      });

      expect(await screen.findByTestId(CARD)).toBeInTheDocument();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the list fails to load', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.getTemplates.mockRejectedValueOnce(new Error('offline'));
      renderFlowPad();
      await openRouteMenu();

      await click(await screen.findByText('inlineRouteTemplateRetry'));

      expect(errorLog).toHaveBeenCalledWith('FlowPad template list fetch failed:', expect.any(Error));
      expect(await screen.findByTestId(CARD)).toBeInTheDocument();
    });

    it('asks once for a list that fails to load and waits for the user to retry', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.getTemplates.mockImplementation(
        () => new Promise((_, reject) => setTimeout(() => reject(new Error('offline')), 5)),
      );
      renderFlowPad();
      await openRouteMenu();
      const retry = await screen.findByText('inlineRouteTemplateRetry');

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
      });
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);

      mocks.getTemplates.mockResolvedValueOnce([TEAM_TEMPLATE]);
      await click(retry);

      expect(await screen.findByTestId(CARD)).toBeInTheDocument();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(2);
    });

    it('keeps waiting for the retry when the menu is closed and opened again in the same session', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.getTemplates.mockRejectedValueOnce(new Error('offline'));
      renderFlowPad();
      await openRouteMenu();
      await screen.findByText('inlineRouteTemplateRetry');

      await click(routeTrigger());
      await openRouteMenu();

      expect(screen.getByText('inlineRouteTemplateRetry')).toBeInTheDocument();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(1);
    });

    it('tries a list that failed again when the next pad session opens the menu', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.getTemplates.mockRejectedValueOnce(new Error('offline'));
      renderFlowPad();
      await openRouteMenu();
      await screen.findByText('inlineRouteTemplateRetry');

      act(() => useFlowPadStore.getState().close());
      act(() => openInlinePad());
      await openRouteMenu();

      expect(await screen.findByTestId(CARD)).toBeInTheDocument();
      expect(mocks.getTemplates).toHaveBeenCalledTimes(2);
    });

    it('filters by the search text and reports the surface view and the first search once', async () => {
      renderFlowPad();
      await openRouteMenu();
      await screen.findByTestId(CARD);
      expect(mocks.metrics.surfaceViewed).toHaveBeenCalledTimes(1);
      expect(mocks.metrics.surfaceViewed).toHaveBeenCalledWith('flow_pad_inline', 'flowpad:inline');

      const search = screen.getByLabelText('inlineRouteTemplateSearchPlaceholder');
      fireEvent.change(search, { target: { value: '   ' } });
      expect(mocks.metrics.searchUsed).not.toHaveBeenCalled();
      fireEvent.change(search, { target: { value: '  Cloud ' } });
      expect(mocks.metrics.searchUsed).toHaveBeenCalledTimes(1);
      expect(mocks.metrics.searchUsed).toHaveBeenCalledWith('flow_pad_inline', 5, 'flowpad:inline');
      fireEvent.change(search, { target: { value: 'zzz' } });

      expect(screen.getByText('inlineRouteTemplateNoResults')).toBeInTheDocument();
      expect(mocks.metrics.searchUsed).toHaveBeenCalledTimes(1);
      await click(routeTrigger());
      await openRouteMenu();
      expect(mocks.metrics.surfaceViewed).toHaveBeenCalledTimes(1);
    });
  });

  describe('pad sessions', () => {
    it('starts each session with an empty search and reports the surface view again', async () => {
      renderFlowPad();
      await openRouteMenu();
      const searchLabel = 'inlineRouteTemplateSearchPlaceholder';
      fireEvent.change(await screen.findByLabelText(searchLabel), { target: { value: 'cloud' } });
      expect(mocks.metrics.surfaceViewed).toHaveBeenCalledTimes(1);
      expect(mocks.metrics.searchUsed).toHaveBeenCalledTimes(1);

      act(() => useFlowPadStore.getState().close());
      act(() => openInlinePad());
      await openRouteMenu();

      expect(screen.getByLabelText(searchLabel)).toHaveValue('');
      expect(mocks.metrics.surfaceViewed).toHaveBeenCalledTimes(2);
      fireEvent.change(screen.getByLabelText(searchLabel), { target: { value: 'cloud' } });
      expect(mocks.metrics.searchUsed).toHaveBeenCalledTimes(2);
    });
  });

  describe('summoning an expert', () => {
    it('summons from the card, refreshes the roster, routes to the new agent and reports the funnel', async () => {
      renderFlowPad();
      await summonFrom(CARD);

      expect(mocks.instantiateTemplate).toHaveBeenCalledWith({
        templateId: 'cloudq-team-template',
        surface: 'flow_pad_inline',
        trigger: 'template_card',
        templateKind: 'team',
        fromSearch: false,
        usedUseCase: false,
        contextKey: 'flowpad:inline',
      });
      expect(agentState.fetchAgents).toHaveBeenCalledTimes(2);
      expect(agentState.fetchAgents).toHaveBeenLastCalledWith(1, 100, true);
      expect(agentState.fetchAgent).toHaveBeenCalledWith('cloudq-instance', expect.any(AbortSignal));
      expect(routeTrigger()).toHaveTextContent('CloudQ Team');
      expect(mocks.metrics.routeApplied).toHaveBeenCalledWith('flow_pad_inline', 'template_card', {
        ...FUNNEL,
        fromSearch: false,
        usedUseCase: false,
      });
      expect(screen.getByRole('textbox')).toHaveValue('');
    });

    it('prefills the chosen use case and marks a summon that came from a search', async () => {
      renderFlowPad();
      await openRouteMenu();
      fireEvent.change(screen.getByLabelText('inlineRouteTemplateSearchPlaceholder'), { target: { value: 'cloud' } });

      await click(await screen.findByTestId(FIRST_USE_CASE));

      expect(screen.getByRole('textbox')).toHaveValue('Diagnose cloud outage');
      expect(mocks.metrics.routeApplied).toHaveBeenCalledWith('flow_pad_inline', 'use_case_chip', {
        ...FUNNEL,
        fromSearch: true,
        usedUseCase: true,
      });

      await submitText('go');
      expect(mocks.metrics.firstMessageSent).toHaveBeenCalledWith('flow_pad_inline', 'use_case_chip', {
        ...FUNNEL,
        fromSearch: true,
        usedUseCase: true,
      });
    });

    it('keeps a draft the user already typed when a use case is chosen', async () => {
      renderFlowPad();
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'my own words' } });

      await summonFrom(FIRST_USE_CASE);

      expect(screen.getByRole('textbox')).toHaveValue('my own words');
    });

    it('hides an earlier route-switch failure hint as soon as a summon starts', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      agentState.fetchAgent.mockResolvedValueOnce(null);
      mocks.instantiateTemplate.mockRejectedValueOnce(new Error('quota exceeded'));
      renderFlowPad();
      await chooseRouteAgent('writer-agent');
      expect(await screen.findByText('inlineRouteSwitchFailedHint')).toBeInTheDocument();

      await summonFrom(CARD);

      expect(screen.queryByText('inlineRouteSwitchFailedHint')).not.toBeInTheDocument();
    });

    it('reports a failed route apply and attributes no message to the summon', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      agentState.fetchAgent.mockResolvedValueOnce(null);
      renderFlowPad();

      await summonFrom(CARD);

      expect(mocks.metrics.routeApplyFailed).toHaveBeenCalledWith('flow_pad_inline', 'template_card', {
        ...FUNNEL,
        fromSearch: false,
        usedUseCase: false,
      });
      expect(mocks.metrics.routeApplied).not.toHaveBeenCalled();
      expect(routeTrigger()).toHaveTextContent('inlineRouteCurrent');
      await submitText('hello');
      expect(mocks.metrics.firstMessageSent).not.toHaveBeenCalled();
    });

    it.each([
      [new Error('quota exceeded'), 'quota exceeded'],
      [new Error('  '), 'inlineRouteTemplateApplyFailed'],
    ])('tells the user why a summon failed (%s) and lets them try again', async (failure, shown) => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.instantiateTemplate.mockRejectedValueOnce(failure);
      renderFlowPad();

      await summonFrom(CARD);

      expect(mocks.toast.error).toHaveBeenCalledWith(shown, { duration: 3000 });
      expect(mocks.metrics.routeApplied).not.toHaveBeenCalled();
      expect(screen.getByTestId(CARD)).toBeEnabled();
    });

    it('reports the first message after a summon exactly once', async () => {
      renderFlowPad();
      await summonFrom(FIRST_USE_CASE);

      await submitText('first');
      await submitText('second');

      expect(mocks.metrics.firstMessageSent).toHaveBeenCalledTimes(1);
      expect(mocks.metrics.firstMessageSent).toHaveBeenCalledWith('flow_pad_inline', 'use_case_chip', {
        ...FUNNEL,
        fromSearch: false,
        usedUseCase: true,
      });
      expect(chatState.sendMessage.mock.calls[0][5]).toMatchObject({ agentId: 'cloudq-instance' });
    });

    it('stops attributing messages to a summon once another agent is picked', async () => {
      renderFlowPad();
      await summonFrom(CARD);

      await chooseRouteAgent('writer-agent');
      await submitText('hello');

      expect(mocks.metrics.firstMessageSent).not.toHaveBeenCalled();
      expect(chatState.sendMessage.mock.calls[0][5]).toMatchObject({ agentId: 'writer-agent' });
    });
  });
});
