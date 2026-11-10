/** @vitest-environment jsdom */
import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import {
  agentDetail,
  agentState,
  chatState,
  chooseRouteAgent,
  click,
  deferred,
  mocks,
  openChatPad,
  openInlinePad,
  openRouteMenu,
  renderFlowPad,
  rerenderFlowPad,
  resetFlowPadKit,
  routeTrigger,
  simulateChatChange,
  submitText,
} from './flowPadTestKit';

describe('FlowPadModal: inline route', () => {
  beforeEach(() => {
    resetFlowPadKit();
    openInlinePad();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('roster', () => {
    it('refreshes the whole roster once when the inline pad opens', () => {
      renderFlowPad();

      expect(agentState.fetchAgents).toHaveBeenCalledTimes(1);
      expect(agentState.fetchAgents).toHaveBeenCalledWith(1, 100, true);
    });

    it('leaves the roster alone for the chat pad', () => {
      openChatPad();
      renderFlowPad();

      expect(agentState.fetchAgents).not.toHaveBeenCalled();
    });

    it('falls back to the session route when the routed agent leaves the roster', async () => {
      const view = renderFlowPad();
      await chooseRouteAgent('writer-agent');
      expect(routeTrigger()).toHaveTextContent('Writer Agent');
      expect(routeTrigger()).toHaveTextContent('inlineRouteProfile');

      agentState.agents = agentState.agents.filter((agent) => agent.id !== 'writer-agent');
      rerenderFlowPad(view);

      expect(routeTrigger()).toHaveTextContent('inlineRouteCurrent');
      expect(routeTrigger()).not.toHaveTextContent('Writer Agent');
      await submitText('hello');
      expect(chatState.sendMessage.mock.calls[0][5]).toBeUndefined();
    });
  });

  describe('route menu', () => {
    it('closes on a press outside it and stays open for a press inside it', async () => {
      renderFlowPad();
      await openRouteMenu();
      const followCurrent = await screen.findByTestId('flowpad-inline-route-follow-current');

      fireEvent.mouseDown(followCurrent);
      expect(screen.getByTestId('flowpad-inline-route-follow-current')).toBeInTheDocument();

      fireEvent.mouseDown(document.body);
      expect(screen.queryByTestId('flowpad-inline-route-follow-current')).not.toBeInTheDocument();
    });

    it('routes to the picked agent with its profile and can return to the session route', async () => {
      renderFlowPad();
      await chooseRouteAgent('writer-agent');

      expect(agentState.fetchAgent).toHaveBeenCalledWith('writer-agent', expect.any(AbortSignal));
      expect(mocks.toast.success).toHaveBeenCalledWith('inlineRouteApplied', { duration: 2000 });
      await submitText('first');
      expect(chatState.sendMessage.mock.calls[0][5]).toMatchObject({ agentId: 'writer-agent' });

      await openRouteMenu();
      await click(screen.getByTestId('flowpad-inline-route-follow-current'));
      expect(routeTrigger()).toHaveTextContent('inlineRouteCurrent');
      await submitText('second');
      expect(chatState.sendMessage.mock.calls[1][5]).toBeUndefined();
    });

    it("shows the avatar of the picked agent in place of the session agent's", async () => {
      chatState.agentConfig = { agentName: 'TestAgent', avatarUrl: 'https://img.example/current.png' };
      renderFlowPad();
      expect(screen.getByAltText('TestAgent')).toHaveAttribute('src', 'https://img.example/current.png');

      await chooseRouteAgent('writer-agent');

      expect(screen.getByAltText('Writer Agent')).toHaveAttribute('src', 'https://img.example/writer.png');
    });

    it('keeps the route and skips the reload when the picked agent is already selected', async () => {
      renderFlowPad();
      await chooseRouteAgent('writer-agent');

      await chooseRouteAgent('writer-agent');

      expect(agentState.fetchAgent).toHaveBeenCalledTimes(1);
      expect(routeTrigger()).toHaveTextContent('Writer Agent');
    });

    it('does not let a switch abandoned by a closed pad end the switch of the next session', async () => {
      const abandoned = deferred<ReturnType<typeof agentDetail>>();
      const current = deferred<ReturnType<typeof agentDetail>>();
      agentState.fetchAgent
        .mockImplementationOnce(() => abandoned.promise)
        .mockImplementationOnce(() => current.promise);
      renderFlowPad();
      await chooseRouteAgent('writer-agent');

      act(() => useFlowPadStore.getState().close());
      act(() => openInlinePad());
      await chooseRouteAgent('builtin-general');
      await act(async () => {
        abandoned.resolve(agentDetail('writer-agent'));
      });

      await submitText('hello');
      expect(mocks.toast.warning).toHaveBeenCalledWith('inlineRouteSwitchingBlocked', { duration: 2000 });
      expect(chatState.sendMessage).not.toHaveBeenCalled();
      expect(mocks.toast.success).not.toHaveBeenCalled();

      await act(async () => {
        current.resolve(agentDetail('builtin-general'));
      });
      expect(routeTrigger()).toHaveTextContent('General Assistant');
    });

    it('forgets a failed switch hint when the pad is opened again', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      agentState.fetchAgent.mockResolvedValueOnce(null);
      renderFlowPad();
      await chooseRouteAgent('writer-agent');
      expect(await screen.findByText('inlineRouteSwitchFailedHint')).toBeInTheDocument();

      act(() => useFlowPadStore.getState().close());
      act(() => openInlinePad());

      expect(screen.queryByText('inlineRouteSwitchFailedHint')).not.toBeInTheDocument();
    });

    it('keeps the session route and offers a fallback when the target profile cannot be loaded', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      agentState.fetchAgent.mockResolvedValueOnce(null);
      renderFlowPad();

      await chooseRouteAgent('writer-agent');

      expect(await screen.findByText('inlineRouteSwitchFailedHint')).toBeInTheDocument();
      expect(mocks.toast.error).toHaveBeenCalledWith('inlineRouteApplyFailed', { duration: 3000 });
      expect(routeTrigger()).toHaveTextContent('inlineRouteCurrent');
      await click(screen.getByTestId('flowpad-inline-route-fallback-current'));
      expect(mocks.toast.success).toHaveBeenCalledWith('inlineRouteFallbackApplied', { duration: 2000 });
      expect(screen.queryByText('inlineRouteSwitchFailedHint')).not.toBeInTheDocument();
    });

    it('stays silent when a route switch fails after the pad was closed', async () => {
      const pending = deferred<ReturnType<typeof agentDetail>>();
      agentState.fetchAgent.mockImplementationOnce(() => pending.promise);
      renderFlowPad();
      await chooseRouteAgent('writer-agent');

      act(() => useFlowPadStore.getState().close());
      await act(async () => {
        pending.reject(new Error('late failure'));
      });

      expect(mocks.toast.error).not.toHaveBeenCalled();
    });

    it('ends the generating state when an unrelated chat turn finishes with no inline request', () => {
      renderFlowPad();
      useFlowPadStore.setState({ inlineGenerating: true });

      act(() => simulateChatChange({ loading: true }));
      expect(useFlowPadStore.getState().inlineGenerating).toBe(true);
      act(() => simulateChatChange({ loading: false }));

      expect(useFlowPadStore.getState().inlineGenerating).toBe(false);
    });
  });
});
