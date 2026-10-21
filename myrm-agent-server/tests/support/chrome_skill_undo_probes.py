"""Page probes that explain a missing Task Steps undo hint.

The hint reads the skill step's batch id from the chat store's Task Steps, so a page that is still loading the chat or
failed to load it shows none. The trace installed before a live turn records every change to those steps, so a failed
run tells apart "the store never received the step" from "the page swapped its store mid-turn". The shared dev UI
hot-reloads whenever anyone saves a frontend file, which is the one way a healthy turn ends with a store that never
saw the skill step.
"""

from __future__ import annotations

import os
from pathlib import Path

_FRONTEND_SRC = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src"
_TRACE_TAIL = 60

# Subscribes to the store that exists now and keeps one entry per distinct change of the last assistant message's
# Task Steps (token streaming changes the content, not the steps, so it adds nothing).
INSTALL_UNDO_TRACE_JS = """(() => {
  const store = window.__myrmChatStore;
  if (!store?.subscribe || !store?.getState) return { ok: false, err: 'chat store is not exposed' };
  const startedAt = performance.now();
  const events = [];
  let previous = '';
  store.subscribe((state) => {
    const assistant = (state.messages ?? []).filter((message) => message.role === 'assistant').pop();
    const stepList = assistant?.progressSteps?.length ? assistant.progressSteps : (assistant?.metadata?.progressSteps ?? []);
    const entry = {
      messages: state.messages?.length ?? 0,
      assistantId: assistant?.messageId ?? null,
      loading: state.loading,
      steps: stepList.map((step) => [step.tool_name ?? step.step_key, step.status ?? null, Boolean(step.skill_mutation_batch_id)]),
    };
    const signature = JSON.stringify(entry);
    if (signature === previous || events.length >= 300) return;
    previous = signature;
    events.push({ atMs: Math.round(performance.now() - startedAt), ...entry });
  });
  window.__E2E_UNDO_TRACE__ = { store, events };
  return { ok: true };
})()"""

# What the page holds for the chat: where the page is and how far the store got loading the chat (a chat that is still
# loading or failed to load shows no Task Steps at all, and the hint stays hidden while the last message is loading),
# the store's Task Steps, whether the store is still the one the trace subscribed to, and the trace.
UNDO_STATE_JS = (
    """(() => {
  const state = window.__myrmChatStore?.getState?.();
  const assistants = (state?.messages ?? []).filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  const steps = last?.progressSteps?.length ? last.progressSteps : (last?.metadata?.progressSteps ?? []);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  const trace = window.__E2E_UNDO_TRACE__ ?? null;
  return {
    path: location.pathname,
    chatId: state?.chatId ?? null,
    isMessagesLoaded: state?.isMessagesLoaded ?? null,
    loadError: state?.loadError ?? null,
    notFound: state?.notFound ?? null,
    loading: state?.loading ?? null,
    messageCount: state?.messages?.length ?? 0,
    assistantCount: assistants.length,
    lastAssistantId: last?.messageId ?? null,
    storeSteps: steps.map((step) => ({
      tool: step.tool_name ?? null,
      key: step.step_key ?? null,
      callId: step.tool_call_id ?? null,
      status: step.status ?? null,
      batch: step.skill_mutation_batch_id ?? null,
      error: String(step.error ?? '').slice(0, 160) || null,
    })),
    hasToggle: Boolean(toggle),
    toggleExpanded: toggle?.getAttribute('data-expanded') ?? null,
    hintInDom: Boolean(document.querySelector('[data-testid="skill-manage-undo-hint"]')),
    assistantBubbles: document.querySelectorAll('[data-test-id="assistant-message"]').length,
    storeReplaced: trace ? trace.store !== window.__myrmChatStore : null,
    trace: trace ? trace.events.slice(-__TAIL__) : null,
  };
})()"""
).replace("__TAIL__", str(_TRACE_TAIL))


def recently_edited_frontend_files(since_epoch: float, *, root: Path = _FRONTEND_SRC, limit: int = 12) -> list[str]:
    """Frontend files saved after ``since_epoch``, newest first: any of them may have hot-reloaded the page under test."""
    edited: list[tuple[float, str]] = []
    for directory, _subdirectories, names in os.walk(root):
        for name in names:
            path = Path(directory) / name
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified > since_epoch:
                edited.append((modified, path.relative_to(root).as_posix()))
    return [relative for _modified, relative in sorted(edited, reverse=True)[:limit]]
