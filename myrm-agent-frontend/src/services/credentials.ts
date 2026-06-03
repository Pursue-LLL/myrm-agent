/**
 * Credentials API service
 */

import { apiRequest } from '@/lib/api';

export interface CredentialFile {
  filename: string;
  size: number;
  upload_time?: string;
  expiry_status?: string;
  expiry_message?: string;
  remaining_days?: number;
}

export interface CredentialListResponse {
  files: CredentialFile[];
}

/**
 * Upload credential file
 */
export async function uploadCredential(file: File, filename?: string): Promise<CredentialFile> {
  const formData = new FormData();
  formData.append('file', file);
  if (filename) {
    formData.append('filename', filename);
  }

  return await apiRequest<CredentialFile>('/credentials/upload', {
    method: 'POST',
    body: formData,
  });
}

/**
 * List all credential files
 */
export async function listCredentials(): Promise<CredentialFile[]> {
  const response = await apiRequest<CredentialListResponse>('/credentials');
  return response.files;
}

/**
 * Delete credential file
 */
export async function deleteCredential(filename: string): Promise<void> {
  await apiRequest(`/credentials/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
}

export interface VaultCredential {
  id: string;
  label: string;
  description?: string;
  has_password: boolean;
  has_totp_seed: boolean;
}

export interface VaultCredentialCreate {
  label: string;
  password?: string;
  totp_seed?: string;
  description?: string;
}

export interface VaultCredentialUpdate {
  password?: string;
  totp_seed?: string;
  description?: string;
}

/**
 * List all vault credentials
 */
export async function listVaultCredentials(): Promise<VaultCredential[]> {
  return await apiRequest<VaultCredential[]>('/security/vault-credentials');
}

/**
 * Create vault credential
 */
export async function createVaultCredential(data: VaultCredentialCreate): Promise<VaultCredential> {
  return await apiRequest<VaultCredential>('/security/vault-credentials', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Update vault credential
 */
export async function updateVaultCredential(label: string, data: VaultCredentialUpdate): Promise<VaultCredential> {
  return await apiRequest<VaultCredential>(`/security/vault-credentials/${encodeURIComponent(label)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Delete vault credential
 */
export async function deleteVaultCredential(label: string): Promise<void> {
  await apiRequest(`/security/vault-credentials/${encodeURIComponent(label)}`, {
    method: 'DELETE',
  });
}
