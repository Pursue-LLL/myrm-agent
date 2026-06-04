/**
 * [INPUT]
 * ./knownSseEventTypes::KNOWN_SSE_EVENT_TYPE_VALUES, normalizeSseEventType (POS: SSE type 白名单)
 * ./types::AgentStreamEvent (POS: 全部 SSE 事件的 discriminated union)
 *
 * [OUTPUT]
 * SSEEnvelopeSchema, parseSseEnvelope, SseEnvelope
 *
 * [POS]
 * SSE 行 JSON 校验层：拒绝未知 type，规范化 harness 别名后再交给 reducer。
 */

import * as z from 'zod';
import {
  isKnownSseEventType,
  normalizeSseEventType,
  KNOWN_SSE_EVENT_TYPE_VALUES,
} from './knownSseEventTypes';
import type { AgentStreamEvent } from './types';

const sseEventTypeSchema = z.enum(KNOWN_SSE_EVENT_TYPE_VALUES);

const sseEnvelopeBaseSchema = z
  .object({
    type: z.string(),
    messageId: z.string().optional(),
    error: z.string().optional(),
    error_type: z.string().optional(),
    compression_exhausted: z.boolean().optional(),
    data: z.unknown().optional(),
  })
  .catchall(z.unknown());

export type SseEnvelope = z.infer<typeof sseEnvelopeBaseSchema> & { type: string };

/** @deprecated Use parseSseEnvelope; kept for imports that only need loose shape. */
export const BaseAgentEventSchema = sseEnvelopeBaseSchema;

export const SSEEnvelopeSchema = sseEnvelopeBaseSchema;

/**
 * Validates SSE payload and returns a normalized envelope for the stream reducer.
 * Returns null when JSON is invalid or event type is not in the known set.
 */
export function parseSseEnvelope(raw: unknown): AgentStreamEvent | null {
  const parsed = sseEnvelopeBaseSchema.safeParse(raw);
  if (!parsed.success) {
    return null;
  }
  const envelope = parsed.data;
  if (!isKnownSseEventType(envelope.type)) {
    return null;
  }
  const normalizedType = normalizeSseEventType(envelope.type);
  const typeCheck = sseEventTypeSchema.safeParse(normalizedType);
  if (!typeCheck.success) {
    return null;
  }
  return {
    ...envelope,
    type: normalizedType,
  } as AgentStreamEvent;
}
