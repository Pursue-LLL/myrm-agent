/**
 * Client Service for Agent Memory Asset Hub & Granular ACL Equipment Slots.
 *
 * [INPUT] memoryHubTypes.ts
 * [OUTPUT] memoryHubService: Unified REST client with resilient offline deterministic fallback.
 * [POS] src/components/features/memory-hub/memoryHubService.ts
 */

import type {
  AclScope,
  AclUpdatePayload,
  AgentEquipmentSummary,
  CreateAssetPayload,
  EquipmentSlot,
  MemoryAsset,
  MemoryAssetType,
} from './memoryHubTypes';

export const DEFAULT_MOCK_ASSETS: MemoryAsset[] = [
  {
    id: 'asset-chat-dev-prefs',
    name: 'Developer Preferences & Code Style',
    description: 'Long-term user preferences for concise typing, PEP8, and modern React hooks.',
    asset_type: 'chat_memory',
    acl_scope: 'team',
    owner_agent_id: 'system',
    project_id: 'default-project',
    allowed_agent_ids: [],
    content_preview: 'User prefers strict typing, zero-any policy, and fast async iteration.',
    tags: ['preferences', 'code-style'],
    size_bytes: 2048,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'asset-skill-fastapi-guru',
    name: 'FastAPI & Async Architect Skill',
    description: 'Specialized skill routines for high-throughput ASGI endpoints and DI management.',
    asset_type: 'skill',
    acl_scope: 'team',
    owner_agent_id: 'system',
    project_id: 'default-project',
    allowed_agent_ids: [],
    content_preview: 'def build_async_router(): ... includes robust error wrappers and DI.',
    tags: ['skill', 'backend', 'fastapi'],
    size_bytes: 4096,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'asset-wiki-open-arch',
    name: 'System Topology & Sandboxing Wiki',
    description: 'Comprehensive knowledge graph documenting agent isolation and Volume mounts.',
    asset_type: 'wiki',
    acl_scope: 'project',
    owner_agent_id: 'agent-arch',
    project_id: 'default-project',
    allowed_agent_ids: [],
    content_preview: 'Root architecture separates harness execution engine from business servers.',
    tags: ['wiki', 'architecture', 'sandbox'],
    size_bytes: 8192,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'asset-code-harness-ast',
    name: 'Myrm Harness AST & Dependency Graph',
    description: 'Extracted symbol graph covering tools, agent loops, and middleware hooks.',
    asset_type: 'code_graph',
    acl_scope: 'project',
    owner_agent_id: 'system',
    project_id: 'default-project',
    allowed_agent_ids: [],
    content_preview: 'digraph G { AgentRunner -> ToolRegistry; ContextEngine -> VectorDB; }',
    tags: ['codegraph', 'ast', 'dependencies'],
    size_bytes: 16384,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'asset-chat-secret-sandbox',
    name: 'Private Security Sandbox Notes',
    description: 'Confidential audit findings restricted solely to the dedicated Security Auditor agent.',
    asset_type: 'chat_memory',
    acl_scope: 'private',
    owner_agent_id: 'agent-security-auditor',
    project_id: 'default-project',
    allowed_agent_ids: ['agent-security-auditor'],
    content_preview: 'E2EE salt rotation vectors and enclave isolated execution keys.',
    tags: ['security', 'confidential'],
    size_bytes: 3072,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

class MemoryHubService {
  private readonly baseUrl = '/api/v1/memory-hub/assets';
  private readonly agentBaseUrl = '/api/v1/agents';

  // In-memory fallback state for offline / disconnected modes
  private fallbackAssets: MemoryAsset[] = [...DEFAULT_MOCK_ASSETS];
  private fallbackEquipment: Record<string, Record<string, string>> = {};

  async listAssets(params?: {
    agentId?: string;
    assetType?: MemoryAssetType;
    aclScope?: AclScope;
    projectId?: string;
  }): Promise<MemoryAsset[]> {
    const query = new URLSearchParams();
    if (params?.agentId) {
      query.set('agent_id', params.agentId);
    }
    if (params?.assetType) {
      query.set('asset_type', params.assetType);
    }
    if (params?.aclScope) {
      query.set('acl_scope', params.aclScope);
    }
    if (params?.projectId) {
      query.set('project_id', params.projectId);
    }

    try {
      const url = `${this.baseUrl}${query.toString() ? `?${query.toString()}` : ''}`;
      const res = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
      if (res.ok) {
        return (await res.json()) as MemoryAsset[];
      }
    } catch {
      // Offline fallback
    }

    return this.fallbackAssets.filter((asset) => {
      if (params?.assetType && asset.asset_type !== params.assetType) {
        return false;
      }
      if (params?.aclScope && asset.acl_scope !== params.aclScope) {
        return false;
      }
      if (asset.acl_scope === 'private' && params?.agentId) {
        return (
          asset.owner_agent_id === params.agentId ||
          asset.allowed_agent_ids.includes(params.agentId)
        );
      }
      return true;
    });
  }

  async getAsset(assetId: string): Promise<MemoryAsset | null> {
    try {
      const res = await fetch(`${this.baseUrl}/${assetId}`);
      if (res.ok) {
        return (await res.json()) as MemoryAsset;
      }
    } catch {
      // Offline fallback
    }
    return this.fallbackAssets.find((a) => a.id === assetId) ?? null;
  }

  async createAsset(
    payload: CreateAssetPayload,
    agentId = 'system',
    projectId = 'default-project',
  ): Promise<MemoryAsset> {
    try {
      const res = await fetch(
        `${this.baseUrl}?agent_id=${encodeURIComponent(agentId)}&project_id=${encodeURIComponent(projectId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
      if (res.ok) {
        return (await res.json()) as MemoryAsset;
      }
    } catch {
      // Offline fallback
    }

    const newAsset: MemoryAsset = {
      id: `asset-${payload.asset_type.slice(0, 4)}-${Math.random().toString(36).slice(2, 8)}`,
      name: payload.name,
      description: payload.description,
      asset_type: payload.asset_type,
      acl_scope: payload.acl_scope,
      owner_agent_id: agentId,
      project_id: projectId,
      allowed_agent_ids: payload.allowed_agent_ids ?? [],
      content_preview: payload.content_preview ?? '',
      tags: payload.tags ?? [],
      size_bytes: 1024,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    this.fallbackAssets.push(newAsset);
    return newAsset;
  }

  async updateAssetAcl(
    assetId: string,
    payload: AclUpdatePayload,
    agentId?: string,
  ): Promise<MemoryAsset | null> {
    try {
      const url = `${this.baseUrl}/${assetId}/acl${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''}`;
      const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        return (await res.json()) as MemoryAsset;
      }
    } catch {
      // Offline fallback
    }

    const idx = this.fallbackAssets.findIndex((a) => a.id === assetId);
    if (idx !== -1) {
      this.fallbackAssets[idx] = {
        ...this.fallbackAssets[idx],
        acl_scope: payload.acl_scope,
        allowed_agent_ids: payload.allowed_agent_ids,
        updated_at: new Date().toISOString(),
      };
      return this.fallbackAssets[idx];
    }
    return null;
  }

  async getAgentEquipment(agentId: string): Promise<AgentEquipmentSummary> {
    try {
      const res = await fetch(`${this.agentBaseUrl}/${agentId}/equipment`);
      if (res.ok) {
        return (await res.json()) as AgentEquipmentSummary;
      }
    } catch {
      // Offline fallback
    }

    const equippedMap = this.fallbackEquipment[agentId] ?? {};
    const slots: EquipmentSlot[] = [
      {
        slot_id: 'slot_chat',
        slot_name: 'Chat Memory Slot',
        allowed_types: ['chat_memory'],
        equipped_asset_id: equippedMap['slot_chat'] ?? null,
        equipped_asset:
          this.fallbackAssets.find((a) => a.id === equippedMap['slot_chat']) ?? null,
      },
      {
        slot_id: 'slot_skill',
        slot_name: 'Skill Artifact Slot',
        allowed_types: ['skill'],
        equipped_asset_id: equippedMap['slot_skill'] ?? null,
        equipped_asset:
          this.fallbackAssets.find((a) => a.id === equippedMap['slot_skill']) ?? null,
      },
      {
        slot_id: 'slot_wiki',
        slot_name: 'Wiki Knowledge Slot',
        allowed_types: ['wiki'],
        equipped_asset_id: equippedMap['slot_wiki'] ?? null,
        equipped_asset:
          this.fallbackAssets.find((a) => a.id === equippedMap['slot_wiki']) ?? null,
      },
      {
        slot_id: 'slot_code',
        slot_name: 'Code Graph Slot',
        allowed_types: ['code_graph'],
        equipped_asset_id: equippedMap['slot_code'] ?? null,
        equipped_asset:
          this.fallbackAssets.find((a) => a.id === equippedMap['slot_code']) ?? null,
      },
    ];

    const totalEquipped = slots.filter((s) => s.equipped_asset_id !== null).length;
    return {
      agent_id: agentId,
      slots,
      total_equipped: totalEquipped,
      max_slots: 4,
    };
  }

  async equipAsset(
    agentId: string,
    slotId: string,
    assetId: string,
  ): Promise<AgentEquipmentSummary> {
    try {
      const res = await fetch(`${this.agentBaseUrl}/${agentId}/equipment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_id: slotId, asset_id: assetId }),
      });
      if (res.ok) {
        return (await res.json()) as AgentEquipmentSummary;
      }
    } catch {
      // Offline fallback
    }

    if (!this.fallbackEquipment[agentId]) {
      this.fallbackEquipment[agentId] = {};
    }
    this.fallbackEquipment[agentId][slotId] = assetId;
    return this.getAgentEquipment(agentId);
  }

  async unequipAsset(agentId: string, slotId: string): Promise<AgentEquipmentSummary> {
    try {
      const res = await fetch(`${this.agentBaseUrl}/${agentId}/equipment/${slotId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        return (await res.json()) as AgentEquipmentSummary;
      }
    } catch {
      // Offline fallback
    }

    if (this.fallbackEquipment[agentId]) {
      delete this.fallbackEquipment[agentId][slotId];
    }
    return this.getAgentEquipment(agentId);
  }
}

export const memoryHubService = new MemoryHubService();
