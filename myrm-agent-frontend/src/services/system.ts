import { apiRequest } from '@/lib/api';

export type IngressRequirementSnapshot = {
  required: boolean;
  has_public_ingress: boolean;
  reasons: string[];
  channels: Record<string, 'outbound' | 'inbound'>;
};

export const systemService = {
  /**
   * Get the computed public ingress base URL.
   */
  async getIngressRequirement(): Promise<IngressRequirementSnapshot> {
    return apiRequest<IngressRequirementSnapshot>(`/system/ingress-requirement?t=${Date.now()}`);
  },

  async getIngressUrl(): Promise<string> {
    const data = await apiRequest<{ ingress_url: string }>(`/system/ingress-url?t=${Date.now()}`);
    return data.ingress_url;
  },

  async getLocalNetwork(port: number): Promise<{ ip: string; url: string; hint: string }> {
    return apiRequest<{ ip: string; url: string; hint: string }>(`/system/local-network?port=${port}`);
  },

  async testIngressHealth(baseUrl: string): Promise<boolean> {
    const normalized = baseUrl.replace(/\/+$/, '');
    const response = await fetch(`${normalized}/api/v1/health`, { method: 'GET' });
    return response.ok;
  },

  /**
   * Export technical support debug zip bundle.
   */
  getSupportDebugBundleUrl(options?: { includeTraces?: boolean; includeProfiles?: boolean }): string {
    const params = new URLSearchParams();
    if (options?.includeTraces !== undefined) {
      params.set('include_traces', String(options.includeTraces));
    }
    if (options?.includeProfiles !== undefined) {
      params.set('include_profiles', String(options.includeProfiles));
    }
    const qs = params.toString();
    return `/api/v1/system/debug-bundle${qs ? `?${qs}` : ''}`;
  },

  /**
   * Storage Governance APIs
   */
  async getStorageGovernanceReport(): Promise<{
    total_storage_bytes: number;
    disk_total_bytes: number;
    disk_free_bytes: number;
    disk_used_percentage: number;
    categories: Array<{
      category: string;
      display_name: string;
      bytes: number;
      item_count: number;
      percentage: number;
      details: Record<string, number>;
    }>;
    snapshots: Array<{
      snapshot_id: string;
      label: string;
      size_bytes: number;
      created_at: string;
      checksum: string;
      file_count: number;
    }>;
    recommended_actions: string[];
    is_growth_healthy: boolean;
    generated_at: string;
  }> {
    return apiRequest(`/system/storage/governance?t=${Date.now()}`);
  },

  async executeStorageCompaction(options?: {
    purge_orphan_checkpoints?: boolean;
    incremental_pages?: number;
  }): Promise<{
    success: boolean;
    initial_bytes: number;
    final_bytes: number;
    freed_bytes: number;
    purged_checkpoints: number;
    wal_truncated: boolean;
    duration_ms: number;
    message: string;
  }> {
    return apiRequest('/system/storage/compaction', {
      method: 'POST',
      body: JSON.stringify({
        purge_orphan_checkpoints: options?.purge_orphan_checkpoints ?? true,
        incremental_pages: options?.incremental_pages ?? 500,
      }),
    });
  },

  async createStateSnapshot(label: string): Promise<{
    success: boolean;
    message: string;
    snapshot?: {
      snapshot_id: string;
      label: string;
      size_bytes: number;
      created_at: string;
      checksum: string;
      file_count: number;
    };
  }> {
    return apiRequest('/system/storage/snapshots', {
      method: 'POST',
      body: JSON.stringify({ label }),
    });
  },

  async restoreStateSnapshot(snapshotId: string): Promise<{
    success: boolean;
    message: string;
  }> {
    return apiRequest(`/system/storage/snapshots/${snapshotId}/restore`, {
      method: 'POST',
    });
  },

  async deleteStateSnapshot(snapshotId: string): Promise<{
    success: boolean;
    message: string;
  }> {
    return apiRequest(`/system/storage/snapshots/${snapshotId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Database storage optimization (FTS B-tree compaction, VACUUM freelist reclaim, WAL truncate)
   */
  async getStorageOptimizePreflight(): Promise<StorageOptimizePreflightResponse> {
    return apiRequest<StorageOptimizePreflightResponse>('/system/storage/optimize-preflight', {
      method: 'POST',
    });
  },

  async executeStorageOptimize(req: StorageOptimizeRequest): Promise<StorageOptimizeResponse> {
    return apiRequest<StorageOptimizeResponse>('/system/storage/optimize', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },
};

export interface DatabaseStorageBreakdown {
  main_db_bytes: number;
  wal_bytes: number;
  shm_bytes: number;
  total_bytes: number;
}

export interface StorageOptimizePreflightResponse {
  data_dir: string;
  db_breakdown: DatabaseStorageBreakdown;
  disk_free_bytes: number;
  can_deep_optimize: boolean;
  recommended_mode: 'deep' | 'light';
  active_background_jobs: number;
  is_safe_to_optimize: boolean;
  reason: string | null;
}

export interface StorageOptimizeRequest {
  mode: 'deep' | 'light';
  create_backup?: boolean;
}

export interface StorageOptimizeResponse {
  status: string;
  mode: string;
  before_bytes: number;
  after_bytes: number;
  reclaimed_bytes: number;
  reclaimed_percentage: number;
  backup_path: string | null;
  duration_ms: number;
  message: string;
}

