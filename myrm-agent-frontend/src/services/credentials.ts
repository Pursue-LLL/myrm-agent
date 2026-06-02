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
