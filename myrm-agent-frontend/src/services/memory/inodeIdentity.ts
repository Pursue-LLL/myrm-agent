/**
 * Directory Inode Identity API client.
 * Connects frontend inspection cards to physical inode resolution,
 * directory rename/move detection, and double-sync prevention guards.
 */

import { apiClient } from '@/services/api';

export interface DirectoryIdentityDTO {
  canonical_path: string;
  device_id: number;
  inode_id: number;
  birth_time_ns: number;
  root_signature: string;
  fs_kind: 'posix' | 'windows' | 'fallback_virtual' | string;
  is_symlink: boolean;
  physical_key: string;
}

export interface ResolveIdentityRequest {
  target_path: string;
}

export interface ResolveIdentityResponse {
  target_path: string;
  real_path: string;
  is_accessible: boolean;
  is_directory: boolean;
  is_symlink: boolean;
  identity: DirectoryIdentityDTO | null;
  error_message?: string | null;
}

export interface KnownIdentityDTO {
  canonical_path: string;
  device_id: number;
  inode_id: number;
  birth_time_ns?: number;
  root_signature?: string;
  fs_kind?: string;
}

export interface VerifySyncRequest {
  target_path: string;
  known_identities: KnownIdentityDTO[];
}

export interface VerifySyncResponse {
  action: 'proceed_incremental' | 'relocate_and_proceed' | 'rebuild_warning' | 'register_new' | 'blocked' | string;
  match_kind: 'exact_match' | 'moved_or_renamed' | 'inode_reused' | 'brand_new' | string;
  reason: string;
  old_path?: string | null;
  new_path: string;
  physical_key: string;
  needs_database_relocation: boolean;
  identity: DirectoryIdentityDTO | null;
}

export interface InodeIdentityHealthResponse {
  status: string;
  module: string;
  version: string;
}

export const inodeIdentityApi = {
  /** Resolve physical device and inode identity for a directory path */
  async resolveIdentity(request: ResolveIdentityRequest): Promise<ResolveIdentityResponse> {
    const res = await apiClient.post<ResolveIdentityResponse>(
      '/api/memory/inode-identity/resolve',
      request
    );
    return res.data;
  },

  /** Verify workspace directory physical identity before sync to detect moves/double-sync */
  async verifySync(request: VerifySyncRequest): Promise<VerifySyncResponse> {
    const res = await apiClient.post<VerifySyncResponse>(
      '/api/memory/inode-identity/verify-sync',
      request
    );
    return res.data;
  },

  /** Retrieve health status of inode identity subsystem */
  async getHealth(): Promise<InodeIdentityHealthResponse> {
    const res = await apiClient.get<InodeIdentityHealthResponse>(
      '/api/memory/inode-identity/health'
    );
    return res.data;
  },
};
