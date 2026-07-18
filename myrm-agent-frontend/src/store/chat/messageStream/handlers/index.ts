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
import { riskEvents } from "./riskEvents";
import { agentControlEvents } from "./agentControlEvents";
import { toolsProgressEvents } from "./toolsProgressEvents";
import { statusStreamEvents } from "./statusStreamEvents";
import { subagentEvents } from "./subagentEvents";
import { fileDiffEvents } from "./fileDiffEvents";
import { toolLifecycleEvents } from "./toolLifecycleEvents";
import { memoryBriefEvents } from "./memoryBriefEvents";
import { routingMetaEvents } from "./routingMetaEvents";
import { messageContentEvents } from "./messageContentEvents";
import { artifactEvents } from "./artifactEvents";
import { captchaEvents } from "./captchaEvents";
import { sessionRecordingEvents } from "./sessionRecordingEvents";
import { modelNotifyEvents } from "./modelNotifyEvents";
import { completionEvents } from "./completionEvents";
import { gapEvents } from "./gapEvents";

export const STREAM_EVENT_HANDLERS: Array<(ctx: StreamCtx) => Promise<StreamTurn | null>> = [
  companionEvents,
  riskEvents,
  rateLimitEvents,
  gapEvents,
  agentControlEvents,
  toolsProgressEvents,
  statusStreamEvents,
  subagentEvents,
  fileDiffEvents,
  toolLifecycleEvents,
  memoryBriefEvents,
  routingMetaEvents,
  messageContentEvents,
  artifactEvents,
  captchaEvents,
  sessionRecordingEvents,
  modelNotifyEvents,
  completionEvents,
];

