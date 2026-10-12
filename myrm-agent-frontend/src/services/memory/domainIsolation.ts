/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Domain Isolation DTOs and API clients:
 * - listConnectorBindings: Fetch bindings of connectors to work or personal domains
 * - setConnectorBinding: Bind an external connector to a specific domain
 * - getConnectorBinding: Retrieve binding info for a connector
 * - deleteConnectorBinding: Remove binding for a connector
 * - listDomainGrants: Fetch grant permissions for work and personal domains
 * - getDomainGrant: Retrieve grant permissions for a specific domain
 * - updateDomainGrant: Update permissions (write, recall, egress) for a domain
 * - validateDomainRecall: Check if cross-domain recall is permitted
 * - validateDomainWrite: Check if write is permitted for a domain
 * - evaluateChannelEgress: Check external channel egress privacy redlines
 *
 * [POS]
 * Frontend API service for Item 156 ConnectionAndAccountDomainIsolation.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export type DataDomain = 'work' | 'personal';

export interface ConnectorDomainBindingDTO {
  connector_id: string;
  channel: string;
  account_id: string | null;
  domain: DataDomain;
  created_at: string;
  updated_at: string;
}

export interface SetConnectorDomainRequest {
  connector_id: string;
  domain: DataDomain;
  channel?: string;
  account_id?: string | null;
}

export interface DomainGrantConfigDTO {
  domain: DataDomain;
  allow_write: boolean;
  allow_recall: boolean;
  allow_proactive: boolean;
  allow_egress: boolean;
}

export interface UpdateDomainGrantRequest {
  allow_write?: boolean;
  allow_recall?: boolean;
  allow_proactive?: boolean;
  allow_egress?: boolean;
}

export interface ValidateRecallRequest {
  target_domain: DataDomain;
  active_domain?: DataDomain;
  allow_cross_domain?: boolean;
}

export interface ValidateRecallResponse {
  allowed: boolean;
  reason: string;
  is_cross_domain: boolean;
}

export interface ValidateWriteRequest {
  domain: DataDomain;
}

export interface ValidateWriteResponse {
  allowed: boolean;
  reason: string;
}

export interface EvaluateEgressRequest {
  content_domain: DataDomain;
  target_channel: string;
  user_confirmed?: boolean;
}

export interface EgressDecisionDTO {
  allowed: boolean;
  requires_user_confirmation: boolean;
  reason: string;
  source_domain: DataDomain;
  target_channel: string;
  is_cross_domain: boolean;
}

export async function listConnectorBindings(domain?: DataDomain): Promise<ConnectorDomainBindingDTO[]> {
  const url = domain
    ? `/memory/domain-isolation/bindings?domain=${encodeURIComponent(domain)}`
    : '/memory/domain-isolation/bindings';
  return apiRequest<ConnectorDomainBindingDTO[]>(url, { method: 'GET' });
}

export async function setConnectorBinding(
  req: SetConnectorDomainRequest
): Promise<ConnectorDomainBindingDTO> {
  return apiRequest<ConnectorDomainBindingDTO>('/memory/domain-isolation/bindings', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getConnectorBinding(
  connectorId: string
): Promise<ConnectorDomainBindingDTO> {
  return apiRequest<ConnectorDomainBindingDTO>(
    `/memory/domain-isolation/bindings/${encodeURIComponent(connectorId)}`,
    { method: 'GET' }
  );
}

export async function deleteConnectorBinding(connectorId: string): Promise<void> {
  return apiRequest<void>(
    `/memory/domain-isolation/bindings/${encodeURIComponent(connectorId)}`,
    { method: 'DELETE' }
  );
}

export async function listDomainGrants(): Promise<DomainGrantConfigDTO[]> {
  return apiRequest<DomainGrantConfigDTO[]>('/memory/domain-isolation/grants', {
    method: 'GET',
  });
}

export async function getDomainGrant(domain: DataDomain): Promise<DomainGrantConfigDTO> {
  return apiRequest<DomainGrantConfigDTO>(
    `/memory/domain-isolation/grants/${encodeURIComponent(domain)}`,
    { method: 'GET' }
  );
}

export async function updateDomainGrant(
  domain: DataDomain,
  req: UpdateDomainGrantRequest
): Promise<DomainGrantConfigDTO> {
  return apiRequest<DomainGrantConfigDTO>(
    `/memory/domain-isolation/grants/${encodeURIComponent(domain)}`,
    {
      method: 'PUT',
      body: JSON.stringify(req),
    }
  );
}

export async function validateDomainRecall(
  req: ValidateRecallRequest
): Promise<ValidateRecallResponse> {
  return apiRequest<ValidateRecallResponse>('/memory/domain-isolation/validate-recall', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function validateDomainWrite(
  req: ValidateWriteRequest
): Promise<ValidateWriteResponse> {
  return apiRequest<ValidateWriteResponse>('/memory/domain-isolation/validate-write', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function evaluateChannelEgress(
  req: EvaluateEgressRequest
): Promise<EgressDecisionDTO> {
  return apiRequest<EgressDecisionDTO>('/memory/domain-isolation/evaluate-egress', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
