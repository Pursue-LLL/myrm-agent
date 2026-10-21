/**
 * [INPUT]
 * @/store/chat/types::Message (POS: 聊天消息模型)
 *
 * [OUTPUT]
 * applyDisclosureMetadata(): 把 message_end 的披露字段（证据档、暂存草案）映射到消息对象
 *
 * [POS]
 * messageStream 披露字段映射器。实时事件与持久化元数据共用同一组键，映射逻辑集中在此以便单测。
 */

import type { Message } from '@/store/chat/types';

export interface DisclosureEventData {
  deliverable_tier?: unknown;
  staged_artifacts?: unknown;
  [key: string]: unknown;
}

export function applyDisclosureMetadata(message: Message, data: object): void {
  const payload = data as DisclosureEventData;

  const deliverableTier = payload.deliverable_tier;
  if (deliverableTier && typeof deliverableTier === 'object') {
    message.deliverableTier = deliverableTier as Message['deliverableTier'];
  }

  const stagedArtifacts = payload.staged_artifacts;
  if (Array.isArray(stagedArtifacts) && stagedArtifacts.length > 0) {
    message.stagedArtifacts = stagedArtifacts as Message['stagedArtifacts'];
  }
}
