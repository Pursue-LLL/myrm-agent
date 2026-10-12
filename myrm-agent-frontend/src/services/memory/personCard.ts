/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Person Card & Relationship Memory DTOs and API clients:
 * - listPersonCards: Retrieve or filter person cards by query, relation, scope
 * - getPersonCard: Retrieve a single person card by ID
 * - createPersonCard: Create a new person card profile
 * - updatePersonCard: Update an existing person card
 * - deletePersonCard: Remove a person card
 * - mergePersonCards: Merge source card into target card
 * - preActionCheck: Perform proactive attribute verification prior to outbound action
 * - refreshPersonDecay: Recalculate continuous gravity decay and weak statuses
 *
 * [POS]
 * Frontend API service for Item 155 PersonCardAndRelationshipMemoryLayer.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export type RelationType =
  | 'self'
  | 'family'
  | 'colleague'
  | 'client'
  | 'vendor'
  | 'recruiter'
  | 'friend'
  | 'other';

export type DecayStatus = 'active' | 'weak' | 'archived';

export type ActionType =
  | 'send_invite'
  | 'send_email'
  | 'create_group'
  | 'assign_task'
  | 'submit_approval'
  | 'other';

export interface PersonAttributesDTO {
  dietary_restrictions: string[];
  birthday?: string | null;
  timezone?: string | null;
  preferred_contact_hours?: string | null;
  approval_preference?: string | null;
  custom_notes: Record<string, string>;
}

export interface PersonInteractionDTO {
  timestamp: string;
  summary: string;
  channel?: string | null;
  source_event_id?: string | null;
}

export interface PersonCardDTO {
  person_id: string;
  display_name: string;
  aliases: string[];
  relation_type: RelationType;
  org?: string | null;
  attributes: PersonAttributesDTO;
  commitments: string[];
  interaction_timeline: PersonInteractionDTO[];
  last_interaction_at?: string | null;
  confidence: number;
  scope: 'global' | 'agent';
  agent_id?: string | null;
  decay_status: DecayStatus;
  decay_score: number;
}

export interface CreatePersonCardRequest {
  person_id?: string;
  display_name: string;
  aliases?: string[];
  relation_type?: RelationType;
  org?: string | null;
  attributes?: Partial<PersonAttributesDTO>;
  commitments?: string[];
  scope?: 'global' | 'agent';
  agent_id?: string | null;
}

export interface UpdatePersonCardRequest {
  display_name?: string;
  aliases?: string[];
  relation_type?: RelationType;
  org?: string | null;
  attributes?: Partial<PersonAttributesDTO>;
  commitments?: string[];
  confidence?: number;
  decay_status?: DecayStatus;
}

export interface ParticipantAttributeSummaryDTO {
  person_id: string;
  display_name: string;
  relation_type: RelationType;
  dietary_restrictions: string[];
  timezone?: string | null;
  approval_preference?: string | null;
  missing_critical_attributes: string[];
  is_weak_memory: boolean;
  attributes: PersonAttributesDTO;
}

export interface PreActionCheckRequestDTO {
  action_type: ActionType;
  participant_names_or_ids: string[];
  action_summary?: string;
  agent_id?: string | null;
}

export interface PreActionCheckResponseDTO {
  action_type: ActionType;
  action_summary: string;
  has_missing_attributes: boolean;
  has_weak_memory_warning: boolean;
  participants: ParticipantAttributeSummaryDTO[];
  prompt_cue: string;
  warnings: string[];
}

export async function listPersonCards(params?: {
  query?: string;
  scope?: 'global' | 'agent';
  relation_type?: RelationType;
  include_weak?: boolean;
  include_archived?: boolean;
  agent_id?: string;
}): Promise<PersonCardDTO[]> {
  const queryParams = new URLSearchParams();
  if (params?.query) queryParams.set('query', params.query);
  if (params?.scope) queryParams.set('scope', params.scope);
  if (params?.relation_type) queryParams.set('relation_type', params.relation_type);
  if (params?.include_weak !== undefined) queryParams.set('include_weak', String(params.include_weak));
  if (params?.include_archived !== undefined) queryParams.set('include_archived', String(params.include_archived));
  if (params?.agent_id) queryParams.set('agent_id', params.agent_id);

  const qs = queryParams.toString();
  const url = qs ? `/memory/person-card?${qs}` : '/memory/person-card';
  return apiRequest<PersonCardDTO[]>(url, { method: 'GET' });
}

export async function getPersonCard(personId: string): Promise<PersonCardDTO> {
  return apiRequest<PersonCardDTO>(`/memory/person-card/${encodeURIComponent(personId)}`, {
    method: 'GET',
  });
}

export async function createPersonCard(req: CreatePersonCardRequest): Promise<PersonCardDTO> {
  return apiRequest<PersonCardDTO>('/memory/person-card', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function updatePersonCard(
  personId: string,
  req: UpdatePersonCardRequest
): Promise<PersonCardDTO> {
  return apiRequest<PersonCardDTO>(`/memory/person-card/${encodeURIComponent(personId)}`, {
    method: 'PUT',
    body: JSON.stringify(req),
  });
}

export async function deletePersonCard(personId: string): Promise<void> {
  return apiRequest<void>(`/memory/person-card/${encodeURIComponent(personId)}`, {
    method: 'DELETE',
  });
}

export async function mergePersonCards(
  sourcePersonId: string,
  targetPersonId: string
): Promise<PersonCardDTO> {
  return apiRequest<PersonCardDTO>('/memory/person-card/merge', {
    method: 'POST',
    body: JSON.stringify({
      source_person_id: sourcePersonId,
      target_person_id: targetPersonId,
    }),
  });
}

export async function preActionCheck(
  req: PreActionCheckRequestDTO
): Promise<PreActionCheckResponseDTO> {
  return apiRequest<PreActionCheckResponseDTO>('/memory/person-card/pre-action-check', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function refreshPersonDecay(weakThreshold = 0.3): Promise<Record<string, number>> {
  return apiRequest<Record<string, number>>(
    `/memory/person-card/refresh-decay?weak_threshold=${weakThreshold}`,
    {
      method: 'POST',
    }
  );
}
