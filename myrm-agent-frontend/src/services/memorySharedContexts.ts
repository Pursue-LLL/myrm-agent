/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Shared Context DTOs and API functions for contexts, bindings, proposals, and history promotion.
 *
 * [POS]
 * Frontend Shared Context API client. Keeps shared-memory collaboration calls separate from core memory CRUD.
 */

import { apiRequest } from '@/lib/api';

export type SharedContextStatus = 'active' | 'archived';
export type SharedContextProposalStatus = 'pending' | 'approved' | 'rejected';
export type SharedContextMemoryType = 'semantic' | 'episodic';
export type SharedContextTargetType = 'agent' | 'channel' | 'cron' | 'conversation' | 'task';

export interface SharedContext {
  id: string;
  namespace: string;
  name: string;
  description: string;
  status: SharedContextStatus;
  policy: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SharedContextListResponse {
  items: SharedContext[];
  total: number;
}

export interface CreateSharedContextRequest {
  name: string;
  description?: string;
  policy?: Record<string, unknown>;
}

export interface UpdateSharedContextRequest {
  name?: string;
  description?: string;
  status?: SharedContextStatus;
  policy?: Record<string, unknown>;
}

export interface SharedContextBinding {
  id: string;
  context_id: string;
  target_type: SharedContextTargetType;
  target_id: string;
  created_at: string;
}

export interface SharedContextBindingListResponse {
  items: SharedContextBinding[];
  total: number;
}

export interface CreateSharedContextBindingRequest {
  target_type: SharedContextTargetType;
  target_id: string;
}

export interface SharedContextWriteProposal {
  id: string;
  context_id: string;
  memory_type: SharedContextMemoryType;
  content: string;
  metadata: Record<string, unknown>;
  source_type: string;
  source_id?: string | null;
  status: SharedContextProposalStatus;
  created_at: string;
  resolved_at?: string | null;
}

export interface SharedContextWriteProposalListResponse {
  items: SharedContextWriteProposal[];
  total: number;
}

export interface CreateSharedContextWriteProposalRequest {
  memory_type: SharedContextMemoryType;
  content: string;
  metadata?: Record<string, unknown>;
  source_type?: string;
  source_id?: string;
}

export interface UpdateSharedContextWriteProposalRequest {
  content?: string;
  metadata?: Record<string, unknown>;
}

export interface SharedContextHistoryMessage {
  message_id: string;
  chat_id: string;
  role: string;
  content: string;
  snippet: string;
  chat_title: string;
  sent_at?: string | null;
}

export interface SharedContextHistorySearchRequest {
  query: string;
  limit?: number;
  offset?: number;
  since?: string;
  until?: string;
}

export interface SharedContextHistorySearchResponse {
  context_id: string;
  query: string;
  items: SharedContextHistoryMessage[];
  total: number;
}

export interface CreateSharedContextProposalFromHistoryRequest {
  message_id: string;
  memory_type: SharedContextMemoryType;
  content?: string;
  metadata?: Record<string, unknown>;
}

export const listSharedContexts = async (status?: SharedContextStatus): Promise<SharedContextListResponse> => {
  const query = status ? `?status=${status}` : '';
  return apiRequest<SharedContextListResponse>(`/memory/shared-contexts/${query}`);
};

export const createSharedContext = async (body: CreateSharedContextRequest): Promise<SharedContext> => {
  return apiRequest<SharedContext>('/memory/shared-contexts/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const updateSharedContext = async (
  contextId: string,
  body: UpdateSharedContextRequest,
): Promise<SharedContext> => {
  return apiRequest<SharedContext>(`/memory/shared-contexts/${contextId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
};

export const archiveSharedContext = async (contextId: string): Promise<SharedContext> => {
  return apiRequest<SharedContext>(`/memory/shared-contexts/${contextId}`, {
    method: 'DELETE',
  });
};

export const listSharedContextBindings = async (contextId: string): Promise<SharedContextBindingListResponse> => {
  return apiRequest<SharedContextBindingListResponse>(`/memory/shared-contexts/${contextId}/bindings`);
};

export const listSharedContextBindingsForTarget = async (
  targetType: SharedContextTargetType,
  targetId: string,
): Promise<SharedContextBindingListResponse> => {
  const encodedTargetId = encodeURIComponent(targetId);
  return apiRequest<SharedContextBindingListResponse>(
    `/memory/shared-contexts/bindings/targets/${targetType}/${encodedTargetId}`,
  );
};

export const createSharedContextBinding = async (
  contextId: string,
  body: CreateSharedContextBindingRequest,
): Promise<SharedContextBinding> => {
  return apiRequest<SharedContextBinding>(`/memory/shared-contexts/${contextId}/bindings`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const deleteSharedContextBinding = async (contextId: string, bindingId: string): Promise<void> => {
  await apiRequest(`/memory/shared-contexts/${contextId}/bindings/${bindingId}`, {
    method: 'DELETE',
  });
};

export const listSharedContextWriteProposals = async (
  contextId: string,
  params: { status?: SharedContextProposalStatus; limit?: number } = {},
): Promise<SharedContextWriteProposalListResponse> => {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.limit) query.set('limit', String(params.limit));
  const qs = query.toString();
  return apiRequest<SharedContextWriteProposalListResponse>(
    `/memory/shared-contexts/${contextId}/proposals${qs ? `?${qs}` : ''}`,
  );
};

export const createSharedContextWriteProposal = async (
  contextId: string,
  body: CreateSharedContextWriteProposalRequest,
): Promise<SharedContextWriteProposal> => {
  return apiRequest<SharedContextWriteProposal>(`/memory/shared-contexts/${contextId}/proposals`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const updateSharedContextWriteProposal = async (
  proposalId: string,
  body: UpdateSharedContextWriteProposalRequest,
): Promise<SharedContextWriteProposal> => {
  return apiRequest<SharedContextWriteProposal>(`/memory/shared-contexts/proposals/${proposalId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
};

export const approveSharedContextWriteProposal = async (proposalId: string): Promise<SharedContextWriteProposal> => {
  return apiRequest<SharedContextWriteProposal>(`/memory/shared-contexts/proposals/${proposalId}/approve`, {
    method: 'POST',
  });
};

export const rejectSharedContextWriteProposal = async (proposalId: string): Promise<SharedContextWriteProposal> => {
  return apiRequest<SharedContextWriteProposal>(`/memory/shared-contexts/proposals/${proposalId}/reject`, {
    method: 'POST',
  });
};

export const searchSharedContextHistory = async (
  contextId: string,
  body: SharedContextHistorySearchRequest,
): Promise<SharedContextHistorySearchResponse> => {
  return apiRequest<SharedContextHistorySearchResponse>(`/memory/shared-contexts/${contextId}/history/search`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const createSharedContextProposalFromHistory = async (
  contextId: string,
  body: CreateSharedContextProposalFromHistoryRequest,
): Promise<SharedContextWriteProposal> => {
  return apiRequest<SharedContextWriteProposal>(`/memory/shared-contexts/${contextId}/proposals/from-history`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
};
