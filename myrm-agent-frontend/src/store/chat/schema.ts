import * as z from 'zod';

export const BaseAgentEventSchema = z
  .object({
    type: z.string(),
    messageId: z.string().optional(),
    error: z.string().optional(),
    error_type: z.string().optional(),
    compression_exhausted: z.boolean().optional(),
    data: z.any().optional(),
  })
  .catchall(z.any());

export const SSEEnvelopeSchema = z
  .object({
    type: z.string(),
    messageId: z.string().optional(),
    error: z.string().optional(),
    error_type: z.string().optional(),
    compression_exhausted: z.boolean().optional(),
    data: z.any().optional(),
  })
  .catchall(z.any());
