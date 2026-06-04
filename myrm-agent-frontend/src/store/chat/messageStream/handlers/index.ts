/**
 * [INPUT]
 * ../streamContext::StreamCtx, StreamTurn (POS: per-event handler context)
 * ./*Events modules (POS: SSE event-domain reducer slices)
 *
 * [OUTPUT]
 * STREAM_EVENT_HANDLERS: ordered list of SSE event handlers
 *
 * [POS]
 * Registry and invocation order for chat SSE reducer slices.
 */

import type { StreamCtx, StreamTurn } from "../streamContext";

import { companionEvents } from "./companionEvents";
import { rateLimitEvents } from "./rateLimitEvents";
import { agentControlEvents } from "./agentControlEvents";
import { toolsProgressEvents } from "./toolsProgressEvents";
import { statusStreamEvents } from "./statusStreamEvents";
import { subagentEvents } from "./subagentEvents";
import { fileDiffEvents } from "./fileDiffEvents";
import { toolLifecycleEvents } from "./toolLifecycleEvents";
import { routingMetaEvents } from "./routingMetaEvents";
import { messageContentEvents } from "./messageContentEvents";
import { artifactEvents } from "./artifactEvents";
import { captchaEvents } from "./captchaEvents";
import { modelNotifyEvents } from "./modelNotifyEvents";
import { completionEvents } from "./completionEvents";

export const STREAM_EVENT_HANDLERS: Array<(ctx: StreamCtx) => Promise<StreamTurn | null>> = [
  companionEvents,
  rateLimitEvents,
  agentControlEvents,
  toolsProgressEvents,
  statusStreamEvents,
  subagentEvents,
  fileDiffEvents,
  toolLifecycleEvents,
  routingMetaEvents,
  messageContentEvents,
  artifactEvents,
  captchaEvents,
  modelNotifyEvents,
  completionEvents,
];

