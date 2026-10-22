/**
 * Client service layer for Bot Mode Group Chat & Hermes Peer Messaging.
 * Implements REST calls to /api/v1/group-chat with resilient local fallback for tests.
 */

import {
  AgentPeerMessageRequest,
  AgentPeerMessageResponse,
  GroupMessage,
  GroupMessageSendRequest,
  GroupParticipant,
  GroupRoom,
  GroupRoomCreateRequest,
  PeerSessionArchive,
} from './groupChatTypes';
import { getDeterministicColor } from './deterministicAvatar';

const API_BASE = '/api/v1/group-chat';

const fallbackRoom: GroupRoom = {
  room_id: 'room_fallback_war_room',
  name: 'Engineering War Room',
  topic: 'Full-stack code architecture and cross-agent peer review',
  created_at_epoch_ms: Date.now() - 3600000,
  participants: [
    {
      participant_id: 'user_me',
      name: 'You (Operator)',
      role: 'human',
      avatar_seed: 'user_me',
      avatar_color: '#0f172a',
      is_avatar_locked: true,
      description: 'Human workspace director',
    },
    {
      participant_id: 'code_architect',
      name: 'Code Architect',
      role: 'assistant_bot',
      avatar_seed: 'code_architect',
      avatar_color: '#6366f1',
      is_avatar_locked: true,
      description: 'System design and refactoring specialist',
    },
    {
      participant_id: 'test_runner',
      name: 'Test Runner',
      role: 'assistant_bot',
      avatar_seed: 'test_runner',
      avatar_color: '#10b981',
      is_avatar_locked: true,
      description: 'Zero-regression test suites validator',
    },
  ],
  messages: [
    {
      message_id: 'msg_init_01',
      room_id: 'room_fallback_war_room',
      sender_id: 'code_architect',
      sender_name: 'Code Architect',
      sender_role: 'assistant_bot',
      content: 'Multi-agent room initialized. Standing by for architecture objectives.',
      mentioned_agent_ids: [],
      timestamp_epoch_ms: Date.now() - 1800000,
    },
  ],
};

export const groupChatService = {
  async listRooms(): Promise<GroupRoom[]> {
    try {
      const res = await fetch(`${API_BASE}/rooms`);
      if (res.ok) {
        return (await res.json()) as GroupRoom[];
      }
    } catch {
      // Fallback below
    }
    return [fallbackRoom];
  },

  async createRoom(req: GroupRoomCreateRequest): Promise<GroupRoom> {
    try {
      const res = await fetch(`${API_BASE}/rooms`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (res.ok) {
        return (await res.json()) as GroupRoom;
      }
    } catch {
      // Fallback
    }

    const participants: GroupParticipant[] = [
      {
        participant_id: 'user_me',
        name: 'You (Operator)',
        role: 'human',
        avatar_seed: 'user_me',
        avatar_color: '#0f172a',
        is_avatar_locked: true,
      },
    ];

    for (const agentId of req.initial_agent_ids) {
      participants.push({
        participant_id: agentId,
        name: agentId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        role: 'assistant_bot',
        avatar_seed: agentId,
        avatar_color: getDeterministicColor(agentId),
        is_avatar_locked: true,
      });
    }

    return {
      room_id: `room_${Date.now()}`,
      name: req.name,
      topic: req.topic,
      participants,
      created_at_epoch_ms: Date.now(),
      messages: [],
    };
  },

  async getRoom(roomId: string): Promise<GroupRoom | null> {
    try {
      const res = await fetch(`${API_BASE}/rooms/${roomId}`);
      if (res.ok) {
        return (await res.json()) as GroupRoom;
      }
    } catch {
      // Fallback
    }
    return fallbackRoom.room_id === roomId ? fallbackRoom : null;
  },

  async postMessage(roomId: string, req: GroupMessageSendRequest): Promise<GroupMessage[]> {
    try {
      const res = await fetch(`${API_BASE}/rooms/${roomId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (res.ok) {
        return (await res.json()) as GroupMessage[];
      }
    } catch {
      // Fallback
    }

    const now = Date.now();
    const userMsg: GroupMessage = {
      message_id: `msg_${now}`,
      room_id: roomId,
      sender_id: req.sender_id,
      sender_name: 'You (Operator)',
      sender_role: 'human',
      content: req.content,
      mentioned_agent_ids: req.mentioned_agent_ids,
      timestamp_epoch_ms: now,
    };

    const result: GroupMessage[] = [userMsg];
    for (const agentId of req.mentioned_agent_ids) {
      result.push({
        message_id: `msg_bot_${agentId}_${now}`,
        room_id: roomId,
        sender_id: agentId,
        sender_name: agentId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        sender_role: 'assistant_bot',
        content: `[@${agentId}] Received mission. Analyzing sub-task for: "${req.content.slice(0, 32)}..."`,
        mentioned_agent_ids: [],
        timestamp_epoch_ms: now + 50,
      });
    }

    return result;
  },

  async sendPeerMessage(req: AgentPeerMessageRequest): Promise<AgentPeerMessageResponse> {
    try {
      const res = await fetch(`${API_BASE}/peer/direct-message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (res.ok) {
        return (await res.json()) as AgentPeerMessageResponse;
      }
    } catch {
      // Fallback
    }

    return {
      peer_message_id: `peer_${Date.now()}`,
      sender_agent_id: req.sender_agent_id,
      target_agent_id: req.target_agent_id,
      query_content: req.content,
      reply_content: `[Fallback Peer Reply] Agent '${req.target_agent_id}' resolved dependency for '${req.sender_agent_id}'.`,
      canonical_chat_id: `canon_${req.sender_agent_id}_${req.target_agent_id}`,
      dispatched_at_epoch_ms: Date.now(),
      latency_ms: 12.4,
    };
  },

  async listPeerArchives(agentId: string): Promise<PeerSessionArchive[]> {
    try {
      const res = await fetch(`${API_BASE}/peer/archives/${agentId}`);
      if (res.ok) {
        return (await res.json()) as PeerSessionArchive[];
      }
    } catch {
      // Fallback
    }

    return [
      {
        canonical_chat_id: `canon_code_architect_${agentId}`,
        peer_agent_id: 'code_architect',
        peer_agent_name: 'Code Architect',
        last_message: 'Verified interface contract alignment.',
        message_count: 4,
        updated_at_epoch_ms: Date.now() - 60000,
      },
    ];
  },
};
