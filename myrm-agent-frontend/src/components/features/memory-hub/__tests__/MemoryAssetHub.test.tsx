/**
 * Unit tests for MemoryAssetHub top-level dashboard.
 *
 * [INPUT] MemoryAssetHub, memoryHubService
 * [OUTPUT] Full coverage for catalog filtering, search, equipment loadout actions, ACL drawer, and quick asset creation.
 * [POS] src/components/features/memory-hub/__tests__/MemoryAssetHub.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryAssetHub } from '../MemoryAssetHub';
import { memoryHubService, DEFAULT_MOCK_ASSETS } from '../memoryHubService';
import type { AgentEquipmentSummary } from '../memoryHubTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    hubTitle: 'Agent Cognitive Memory Hub & Equipment Deck',
    hubSubtitle: 'Four-tier memory asset catalog with granular ACL isolation and game-like loadout equipment',
    refresh: 'Refresh',
    createAsset: 'Capture Asset',
    tabAll: 'All Assets',
    typeChatMemory: 'Chat Memory',
    typeSkill: 'Skill Artifact',
    typeWiki: 'Wiki Knowledge',
    typeCodeGraph: 'Code Graph',
    searchPlaceholder: 'Search assets, tags, or descriptions...',
    aclAll: 'All Scopes',
    aclTeam: 'Team Shared',
    aclPrivate: 'Private Enclave',
    aclProject: 'Project Bound',
    emptyResults: 'No cognitive assets match your filters',
    emptyResultsHint: 'Try adjusting your search terms or create a new cognitive memory asset.',
    equipmentLoadout: 'Cognitive Memory Equipment Loadout',
    equipmentSubtitle: 'Mounted memory assets active in the current cognitive loop',
    equippedSlotsCount: 'slots',
    unequip: 'Unequip',
    clickToMount: 'Available for mount',
    equipped: 'Equipped',
    equip: 'Equip',
    configureAcl: 'Configure ACL',
    aclDrawerTitle: 'Granular ACL Security Policy',
    selectAclScope: 'Access Scope Isolation',
    authorizedAgentsLabel: 'Explicit Authorized Agent IDs (comma separated)',
    saveAclPolicy: 'Save ACL Policy',
    cancel: 'Cancel',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MemoryAssetHub', () => {
  const initialEquipment: AgentEquipmentSummary = {
    agent_id: 'test-agent',
    slots: [
      {
        slot_id: 'slot_chat',
        slot_name: 'Chat Memory Slot',
        allowed_types: ['chat_memory'],
        equipped_asset_id: null,
        equipped_asset: null,
      },
      {
        slot_id: 'slot_skill',
        slot_name: 'Skill Artifact Slot',
        allowed_types: ['skill'],
        equipped_asset_id: null,
        equipped_asset: null,
      },
      {
        slot_id: 'slot_wiki',
        slot_name: 'Wiki Knowledge Slot',
        allowed_types: ['wiki'],
        equipped_asset_id: null,
        equipped_asset: null,
      },
      {
        slot_id: 'slot_code',
        slot_name: 'Code Graph Slot',
        allowed_types: ['code_graph'],
        equipped_asset_id: null,
        equipped_asset: null,
      },
    ],
    total_equipped: 0,
    max_slots: 4,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(memoryHubService, 'listAssets').mockResolvedValue([...DEFAULT_MOCK_ASSETS]);
    vi.spyOn(memoryHubService, 'getAgentEquipment').mockResolvedValue(initialEquipment);
    vi.spyOn(memoryHubService, 'equipAsset').mockImplementation(async (agentId, slotId, assetId) => {
      const asset = DEFAULT_MOCK_ASSETS.find((a) => a.id === assetId) ?? null;
      return {
        ...initialEquipment,
        total_equipped: 1,
        slots: initialEquipment.slots.map((s) =>
          s.slot_id === slotId ? { ...s, equipped_asset_id: assetId, equipped_asset: asset } : s,
        ),
      };
    });
    vi.spyOn(memoryHubService, 'unequipAsset').mockResolvedValue(initialEquipment);
    vi.spyOn(memoryHubService, 'updateAssetAcl').mockResolvedValue(DEFAULT_MOCK_ASSETS[0]);
    vi.spyOn(memoryHubService, 'createAsset').mockResolvedValue({
      id: 'asset-new-1',
      name: 'Newly Captured Asset',
      description: 'Captured at runtime',
      asset_type: 'wiki',
      acl_scope: 'team',
      owner_agent_id: 'test-agent',
      project_id: 'default-project',
      allowed_agent_ids: [],
      content_preview: 'Content',
      tags: [],
      size_bytes: 1024,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  it('renders dashboard with catalog and equipment deck', async () => {
    render(<MemoryAssetHub agentId="test-agent" projectId="default-project" />);

    await waitFor(() => {
      expect(screen.getByText('Agent Cognitive Memory Hub & Equipment Deck')).toBeDefined();
    });

    // Check that default assets are listed
    expect(screen.getByText('Developer Preferences & Code Style')).toBeDefined();
    expect(screen.getByText('FastAPI & Async Architect Skill')).toBeDefined();
    expect(screen.getByText('System Topology & Sandboxing Wiki')).toBeDefined();
  });

  it('filters assets by category tab', async () => {
    render(<MemoryAssetHub agentId="test-agent" projectId="default-project" />);

    await waitFor(() => {
      expect(screen.getByText('Developer Preferences & Code Style')).toBeDefined();
    });

    // Click "Wiki Knowledge" Tab
    const wikiTab = screen.getByTestId('tab-wiki');
    fireEvent.click(wikiTab);

    // Only Wiki assets should be visible now
    expect(screen.getByText('System Topology & Sandboxing Wiki')).toBeDefined();
    expect(screen.queryByText('FastAPI & Async Architect Skill')).toBeNull();
  });

  it('equips asset into matching slot when clicking Equip', async () => {
    render(<MemoryAssetHub agentId="test-agent" projectId="default-project" />);

    await waitFor(() => {
      expect(screen.getByTestId('equip-btn-asset-chat-dev-prefs')).toBeDefined();
    });

    const equipBtn = screen.getByTestId('equip-btn-asset-chat-dev-prefs');
    fireEvent.click(equipBtn);

    await waitFor(() => {
      expect(memoryHubService.equipAsset).toHaveBeenCalledWith('test-agent', 'slot_chat', 'asset-chat-dev-prefs');
    });
  });

  it('opens ACL drawer, modifies scope and calls updateAssetAcl', async () => {
    render(<MemoryAssetHub agentId="test-agent" projectId="default-project" />);

    await waitFor(() => {
      expect(screen.getByText('Developer Preferences & Code Style')).toBeDefined();
    });

    // Find and click the ACL capsule button for first asset
    const aclButtons = screen.getAllByLabelText('Configure ACL');
    fireEvent.click(aclButtons[0]);

    // Drawer should open
    expect(screen.getByTestId('asset-acl-drawer')).toBeDefined();
    expect(screen.getByText('Granular ACL Security Policy')).toBeDefined();

    // Select Private scope
    const privateOpt = screen.getByTestId('scope-opt-private');
    fireEvent.click(privateOpt);

    // Input allowed agents
    const input = screen.getByTestId('allowed-agents-input');
    fireEvent.change(input, { target: { value: 'agent-security, agent-audit' } });

    // Click Save
    const saveBtn = screen.getByTestId('save-acl-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(memoryHubService.updateAssetAcl).toHaveBeenCalledWith(
        'asset-chat-dev-prefs',
        {
          acl_scope: 'private',
          allowed_agent_ids: ['agent-security', 'agent-audit'],
        },
        'test-agent',
      );
    });
  });

  it('triggers quick asset capture when clicking Capture Asset button', async () => {
    render(<MemoryAssetHub agentId="test-agent" projectId="default-project" />);

    await waitFor(() => {
      expect(screen.getByTestId('create-asset-btn')).toBeDefined();
    });

    const createBtn = screen.getByTestId('create-asset-btn');
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(memoryHubService.createAsset).toHaveBeenCalled();
    });
  });
});
