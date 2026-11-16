/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * ./handlerDeps::ensureAssistantStreamMessage, mergeMessageSources, resolveStreamChatId, sanitizeStreamText (POS: message lookup, source merge and text hygiene helpers)
 * @/lib/chat/mediaGenerated::MEDIA_GENERATED_METADATA_KEY, mergeMediaGeneratedEntries, readMediaGeneratedEntries (POS: media a media tool call registers from its structured result)
 *
 * [OUTPUT]
 * catchupEvents: CATCHUP_SNAPSHOT SSE handler that replaces the assistant message of the turn with the server snapshot (text, reasoning, steps; sources and generated media are merged in) and seeds the stream accumulator with it.
 *
 * [POS]
 * SSE handler for the snapshot a re-attached stream sends first.
 */

import {
  MEDIA_GENERATED_METADATA_KEY,
  mergeMediaGeneratedEntries,
  readMediaGeneratedEntries,
} from '@/lib/chat/mediaGenerated';
import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';

export async function catchupEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type !== 'catchup_snapshot') {
    return null;
  }

  const snap = data.data;
  // The chunks that follow are appended to the accumulator and written back as the whole content, so it has to start
  // from the snapshot or the first chunk would replace everything the page was just handed.
  const snapshotText = H.sanitizeStreamText(snap.content || '');
  ctx.recievedMessage = snapshotText;
  // The media cards of tool calls that finished before the page attached: the stream carries only what comes after.
  const registeredMedia = readMediaGeneratedEntries(snap.media_generated);

  let rowReady = false;
  actions.setMessages((state) => {
    // A turn the transcript does not show yet (the page was reloaded right after its message was sent) gets its row here;
    // taking the last assistant row instead would overwrite the answer of the previous turn.
    const msgIndex = H.ensureAssistantStreamMessage(state.messages, data.messageId, H.resolveStreamChatId(ctx.state));
    if (msgIndex === -1) {
      return;
    }
    rowReady = true;
    const msg = state.messages[msgIndex];
    msg.content = snapshotText;
    msg.thinkingItems = snap.reasoning ? [snap.reasoning] : [];
    msg.progressSteps = snap.progress_steps || [];
    // Never wipe in-stream sources with an empty catchup payload.
    if (Array.isArray(snap.sources) && snap.sources.length > 0) {
      msg.sources = H.mergeMessageSources(msg.sources || [], snap.sources);
    }
    if (registeredMedia.length > 0) {
      msg.metadata = {
        ...msg.metadata,
        [MEDIA_GENERATED_METADATA_KEY]: mergeMediaGeneratedEntries(
          msg.metadata?.[MEDIA_GENERATED_METADATA_KEY],
          registeredMedia,
        ),
      };
    }
  });
  ctx.added = ctx.added || rowReady;
  return done(ctx);
}
