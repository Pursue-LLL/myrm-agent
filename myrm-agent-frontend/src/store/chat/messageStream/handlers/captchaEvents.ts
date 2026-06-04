/**
 * [POS]
 * Chat SSE event handler slice (captchaEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function captchaEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  // CAPTCHA events → render as progress steps so the user sees the status
  if (
    data.type === H.AgentEventType.CAPTCHA_DETECTED ||
    data.type === H.AgentEventType.CAPTCHA_RESOLVED ||
    data.type === H.AgentEventType.CAPTCHA_TIMEOUT
  ) {
    const captchaStatus: NonNullable<H.ProgressItem['status']> =
      data.type === H.AgentEventType.CAPTCHA_DETECTED
        ? 'warning'
        : data.type === H.AgentEventType.CAPTCHA_RESOLVED
          ? 'success'
          : 'error';

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        const steps = state.messages[messageIndex].progressSteps ?? [];
        const captchaStepIdx = steps.findIndex((s) => s.step_key === 'captcha_challenge');
        const step = {
          step_key: 'captcha_challenge',
          items: [
            {
              text: data.data?.reason ?? 'CAPTCHA challenge',
              captcha_type: data.data?.captcha_type,
            },
          ],
          status: captchaStatus,
        };
        if (captchaStepIdx !== -1) {
          steps[captchaStepIdx] = step;
        } else {
          steps.push(step);
        }
        state.messages[messageIndex].progressSteps = steps;
      }
    });
    return done(ctx);
  }

  return null;
}
