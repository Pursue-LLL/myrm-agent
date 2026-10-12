/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 110:
 * PeerCentricEntityGraphAndAgentPersonaCardSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints (/memory/peer-cognition).
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import { apiClient } from '@/services/api';

export type PeerType = 'user_peer' | 'agent_peer' | 'project_peer' | 'reviewer_peer';
export type PeerRelationKind = 'asserts' | 'approves' | 'collaborates_with' | 'governs' | 'depends_on';

export interface PeerIdentityDTO {
  peer_id: string;
  peer_type: PeerType;
  display_name: string;
  role_title: string;
  avatar_or_icon: string;
  created_at: string;
  last_seen_at: string;
}

export interface PeerRelationEdgeDTO {
  edge_id: string;
  source_peer_id: string;
  target_entity_id: string;
  target_is_peer: boolean;
  relation_kind: PeerRelationKind;
  context_note: string;
  weight: number;
  created_at: string;
}

export interface PeerPersonaCardDTO {
  peer_id: string;
  peer_type: PeerType;
  display_name: string;
  core_responsibilities: string[];
  decision_style: string;
  standing_preferences: Record<string, string>;
  interaction_count: number;
  success_rate: number;
  trust_score: number;
  summary_digest: string;
  updated_at: string;
}

export interface PeerCognitionProjectionDTO {
  formatted_prompt_block: string;
  token_cost_estimate: number;
  targeted_peers: string[];
}

export interface RegisterPeerRequest {
  peer_id: string;
  peer_type: PeerType;
  display_name: string;
  role_title?: string;
  avatar_or_icon?: string;
}

export interface AddRelationEdgeRequest {
  edge_id: string;
  source_peer_id: string;
  target_entity_id: string;
  target_is_peer?: boolean;
  relation_kind?: PeerRelationKind;
  context_note?: string;
  weight?: number;
}

export interface UpdatePersonaCardRequest {
  core_responsibilities?: string[];
  decision_style?: string;
  standing_preferences?: Record<string, string>;
  summary_digest?: string;
}

export interface RecordInteractionRequest {
  success: boolean;
  preference_deltas?: Record<string, string>;
}

export interface GenerateProjectionRequest {
  peer_ids: string[];
}

export async function registerPeerIdentity(
  request: RegisterPeerRequest,
): Promise<PeerIdentityDTO> {
  return apiClient.post<PeerIdentityDTO>(
    '/memory/peer-cognition/peers',
    request,
  );
}

export async function listPeerIdentities(
  peerType?: string,
): Promise<PeerIdentityDTO[]> {
  const query = peerType ? `?peer_type=${encodeURIComponent(peerType)}` : '';
  return apiClient.get<PeerIdentityDTO[]>(
    `/memory/peer-cognition/peers${query}`,
  );
}

export async function getPeerIdentity(
  peerId: string,
): Promise<PeerIdentityDTO> {
  return apiClient.get<PeerIdentityDTO>(
    `/memory/peer-cognition/peers/${encodeURIComponent(peerId)}`,
  );
}

export async function getPersonaCard(
  peerId: string,
): Promise<PeerPersonaCardDTO> {
  return apiClient.get<PeerPersonaCardDTO>(
    `/memory/peer-cognition/cards/${encodeURIComponent(peerId)}`,
  );
}

export async function updatePersonaCard(
  peerId: string,
  request: UpdatePersonaCardRequest,
): Promise<PeerPersonaCardDTO> {
  return apiClient.put<PeerPersonaCardDTO>(
    `/memory/peer-cognition/cards/${encodeURIComponent(peerId)}`,
    request,
  );
}

export async function recordInteractionEvent(
  peerId: string,
  request: RecordInteractionRequest,
): Promise<PeerPersonaCardDTO> {
  return apiClient.post<PeerPersonaCardDTO>(
    `/memory/peer-cognition/cards/${encodeURIComponent(peerId)}/interactions`,
    request,
  );
}

export async function addRelationEdge(
  request: AddRelationEdgeRequest,
): Promise<PeerRelationEdgeDTO> {
  return apiClient.post<PeerRelationEdgeDTO>(
    '/memory/peer-cognition/edges',
    request,
  );
}

export async function getEdgesForPeer(
  peerId: string,
): Promise<PeerRelationEdgeDTO[]> {
  return apiClient.get<PeerRelationEdgeDTO[]>(
    `/memory/peer-cognition/edges/${encodeURIComponent(peerId)}`,
  );
}

export async function generatePromptProjection(
  request: GenerateProjectionRequest,
): Promise<PeerCognitionProjectionDTO> {
  return apiClient.post<PeerCognitionProjectionDTO>(
    '/memory/peer-cognition/projection',
    request,
  );
}
