import type { StreamCtx } from '../streamContext';
import * as H from './handlerDeps';

const MAX_DETAIL_ITEMS = 30;

export function applyStatusPhaseData(ctx: StreamCtx, statusData: Record<string, unknown>): void {
  const { data, actions } = ctx;
  const sd = statusData;

  if ('progress_percent' in sd && typeof sd.progress_percent === 'number') {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx !== -1) {
        const steps = state.messages[idx].progressSteps;
        if (steps && steps.length > 0) {
          steps[steps.length - 1].progress_percent = sd.progress_percent as number;
        }
      }
    });
  }

  if (sd.phase === 'clarify' && sd.status === 'resolved') {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx !== -1 && state.messages[idx].clarification) {
        state.messages[idx].clarification!.answered = true;
      }
    });
  }

  if (sd.phase === 'plan_confirm') {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx === -1) return;
      if (sd.status === 'waiting') {
        const planItems = Array.isArray(sd.plan_items) ? sd.plan_items as Array<{ id: string; content: string; status?: string }> : undefined;
        const isGeneralAgent = !!planItems;
        const planText = typeof sd.plan === 'string' ? sd.plan as string
          : planItems ? planItems.map((item, i) => `${i + 1}. ${item.content}`).join('\n') : '';
        state.messages[idx].planConfirmation = {
          plan: planText,
          status: 'waiting',
          planItems,
          totalItems: typeof sd.total_items === 'number' ? sd.total_items as number : undefined,
          goal: typeof sd.goal === 'string' ? sd.goal as string : undefined,
          source: isGeneralAgent ? 'general_agent' : 'deep_research',
        };
      } else if (sd.status === 'resolved') {
        if (state.messages[idx].planConfirmation) {
          state.messages[idx].planConfirmation!.status = sd.modified ? 'edited' : 'confirmed';
        }
      }
    });
  }

  if (sd.phase === 'explore' && sd.status === 'complete' && sd.has_context) {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx !== -1) {
        const steps = state.messages[idx].progressSteps;
        if (steps && steps.length > 0) {
          const chars = typeof sd.context_chars === 'number' ? sd.context_chars : 0;
          steps[steps.length - 1].items = [
            { text: `Found ${Math.round(chars / 1000)}k chars of relevant local knowledge` },
          ];
        }
      }
    });
  }

  if (sd.phase === 'plan' && typeof sd.plan === 'string') {
    const planText = (sd.plan as string).trim();
    if (planText) {
      const planLines = planText
        .split('\n')
        .map((line) => line.replace(/^[\d\-.*]+\s*/, '').trim())
        .filter((line) => line.length > 0)
        .slice(0, 10);

      if (planLines.length > 0) {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            const steps = state.messages[idx].progressSteps;
            if (steps && steps.length > 0) {
              steps[steps.length - 1].items = planLines.map((line) => ({ text: line }));
            }
          }
        });
      }
    }
  }

  if (sd.phase === 'research' && typeof sd.agent_status === 'string') {
    let detailText: string | null = null;

    if (sd.agent_status === 'started' && typeof sd.task === 'string') {
      detailText = (sd.task as string).slice(0, 120);
    } else if (sd.agent_status === 'tool_call' && typeof sd.tool_name === 'string') {
      detailText = sd.tool_name as string;
    }

    if (detailText) {
      actions.setMessages((state) => {
        const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (idx !== -1) {
          const steps = state.messages[idx].progressSteps;
          if (steps && steps.length > 0) {
            const lastStep = steps[steps.length - 1];
            if (!lastStep.items || !Array.isArray(lastStep.items)) {
              lastStep.items = [];
            }
            const items = lastStep.items as { text: string }[];
            items.push({ text: detailText! });
            if (items.length > MAX_DETAIL_ITEMS) {
              items.splice(0, items.length - MAX_DETAIL_ITEMS);
            }
          }
        }
      });
    }
  }

  if (sd.phase === 'research' && typeof sd.cycle === 'number') {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx !== -1) {
        const steps = state.messages[idx].progressSteps;
        if (steps && steps.length > 0) {
          const lastStep = steps[steps.length - 1];
          const cycle = sd.cycle as number;
          const maxCycles = typeof sd.max_cycles === 'number' ? (sd.max_cycles as number) : 0;
          const costUsd = typeof sd.current_cost_usd === 'number' ? (sd.current_cost_usd as number) : 0;
          const cycleLabel = maxCycles > 0 ? `Cycle ${cycle}/${maxCycles}` : `Cycle ${cycle}`;
          if (costUsd > 0) {
            lastStep.items = [{ text: `${cycleLabel} — $${costUsd.toFixed(2)}` }];
          } else {
            lastStep.items = [{ text: cycleLabel }];
          }
        }
      }
    });
  }

  if (sd.phase === 'research' && typeof sd.budget_event === 'string') {
    actions.setMessages((state) => {
      const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (idx !== -1) {
        const steps = state.messages[idx].progressSteps;
        if (steps && steps.length > 0) {
          const lastStep = steps[steps.length - 1];
          const costUsd = typeof sd.current_cost_usd === 'number' ? (sd.current_cost_usd as number) : 0;
          const budgetUsd = typeof sd.budget_usd === 'number' ? (sd.budget_usd as number) : 0;
          const percentUsed = typeof sd.percent_used === 'number' ? (sd.percent_used as number) : 0;
          const isExceeded = sd.budget_event === 'exceeded';
          const costText = budgetUsd > 0 ? ` ($${costUsd.toFixed(2)}/$${budgetUsd.toFixed(2)})` : '';
          const warningText = isExceeded
            ? `Budget exceeded${costText}`
            : `Budget ${Math.round(percentUsed)}% used${costText}`;
          if (!lastStep.items || !Array.isArray(lastStep.items)) {
            lastStep.items = [];
          }
          (lastStep.items as { text: string }[]).push({ text: warningText });
          lastStep.status = isExceeded ? 'warning' : undefined;
        }
      }
    });
  }
}
