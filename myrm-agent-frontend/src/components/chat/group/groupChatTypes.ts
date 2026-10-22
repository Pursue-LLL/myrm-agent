/**
 * TypeScript Data Contracts for Bot Mode Group Chat & Hermes Peer Messaging.
 * Strict zero-any adherence and alignment with FastAPI backend models.
 */

export type ParticipantRole = 'human' | 'assistant_bot' | 'system';

export interface GroupParticipant {
  participant_id: string;
  name: string;
  role: ParticipantRole;
  avatar_seed: string;
  avatar_color: string;
  is_avatar_locked: boolean;
  description?: string | null;
}

export interface GroupMessage {
  message_id: string;
  room_id: string;
  sender_id: string;
  sender_name: string;
  sender_role: ParticipantRole;
  content: string;
  mentioned_agent_ids: string[];
  timestamp_epoch_ms: number;
}

export interface GroupRoom {
  room_id: string;
  name: string;
  topic: string;
  participants: GroupParticipant[];
  created_at_epoch_ms: number;
  messages: GroupMessage[];
}

export interface GroupRoomCreateRequest {
  name: string;
  topic: string;
  initial_agent_ids: string[];
}

export interface GroupMessageSendRequest {
  sender_id: string;
  content: string;
  mentioned_agent_ids: string[];
}

export interface AgentPeerMessageRequest {
  sender_agent_id: string;
  target_agent_id: string;
  content: string;
  context_task_id?: string | null;
}

export interface AgentPeerMessageResponse {
  peer_message_id: string;
  sender_agent_id: string;
  target_agent_id: string;
  query_content: string;
  reply_content: string;
  canonical_chat_id: string;
  dispatched_at_epoch_ms: number;
  latency_ms: number;
}

export interface PeerSessionArchive {
  canonical_chat_id: string;
  peer_agent_id: string;
  peer_agent_name: string;
  last_message: string;
  message_count: number;
  updated_at_epoch_ms: number;
}
