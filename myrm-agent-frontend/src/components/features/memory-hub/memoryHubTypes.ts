/**
 * Domain types for Agent Memory Asset Hub & Granular ACL Equipment Loadout.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain types for 4-tier cognitive memory assets, ACL policies, and equipment slots.
 * [POS] src/components/features/memory-hub/memoryHubTypes.ts
 */

export type MemoryAssetType = 'chat_memory' | 'skill' | 'wiki' | 'code_graph';

export type AclScope = 'private' | 'team' | 'project';

export interface MemoryAsset {
  id: string;
  name: string;
  description: string;
  asset_type: MemoryAssetType;
  acl_scope: AclScope;
  owner_agent_id: string;
  project_id: string;
  allowed_agent_ids: string[];
  content_preview: string;
  tags: string[];
  size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface EquipmentSlot {
  slot_id: string;
  slot_name: string;
  allowed_types: MemoryAssetType[];
  equipped_asset_id: string | null;
  equipped_asset: MemoryAsset | null;
}

export interface AgentEquipmentSummary {
  agent_id: string;
  slots: EquipmentSlot[];
  total_equipped: number;
  max_slots: number;
}

export interface CreateAssetPayload {
  name: string;
  description: string;
  asset_type: MemoryAssetType;
  acl_scope: AclScope;
  content_preview?: string;
  tags?: string[];
  allowed_agent_ids?: string[];
}

export interface AclUpdatePayload {
  acl_scope: AclScope;
  allowed_agent_ids: string[];
}
