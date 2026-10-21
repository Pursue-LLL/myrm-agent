/**
 * Unit tests for MemoryAssetCard component.
 *
 * [INPUT] MemoryAssetCard, MemoryAsset
 * [OUTPUT] Full coverage for tier styling, ACL pill, preview snippet, equip/unequip, and ACL drawer trigger.
 * [POS] src/components/features/memory-hub/__tests__/MemoryAssetCard.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryAssetCard } from '../MemoryAssetCard';
import type { MemoryAsset } from '../memoryHubTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    typeChatMemory: 'Chat Memory',
    typeSkill: 'Skill Artifact',
    typeWiki: 'Wiki Knowledge',
    typeCodeGraph: 'Code Graph',
    aclPrivate: 'Private Enclave',
    aclTeam: 'Team Shared',
    aclProject: 'Project Bound',
    configureAcl: 'Configure ACL',
    equipped: 'Equipped',
    equip: 'Equip',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MemoryAssetCard', () => {
  const mockAsset: MemoryAsset = {
    id: 'asset-test-wiki-1',
    name: 'Distributed Consensus Wiki',
    description: 'Documentation covering Raft election and Paxos states.',
    asset_type: 'wiki',
    acl_scope: 'team',
    owner_agent_id: 'agent-arch',
    project_id: 'default-project',
    allowed_agent_ids: [],
    content_preview: 'Raft consensus ensures consistent state replication.',
    tags: ['raft', 'consensus'],
    size_bytes: 4096,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  it('renders asset details, tier badge, and ACL pill correctly', () => {
    render(<MemoryAssetCard asset={mockAsset} isEquipped={false} />);

    expect(screen.getByText('Distributed Consensus Wiki')).toBeDefined();
    expect(screen.getByText('Wiki Knowledge')).toBeDefined();
    expect(screen.getByText('Team Shared')).toBeDefined();
    expect(screen.getByText(/Raft consensus ensures consistent state replication/)).toBeDefined();
    expect(screen.getByText('#raft')).toBeDefined();
    expect(screen.getByText('Equip')).toBeDefined();
  });

  it('triggers onEquip when Equip button is clicked', () => {
    const onEquip = vi.fn();
    render(<MemoryAssetCard asset={mockAsset} isEquipped={false} onEquip={onEquip} />);

    const equipBtn = screen.getByTestId('equip-btn-asset-test-wiki-1');
    fireEvent.click(equipBtn);
    expect(onEquip).toHaveBeenCalledWith(mockAsset);
  });

  it('renders equipped state and triggers onUnequip when clicked', () => {
    const onUnequip = vi.fn();
    render(<MemoryAssetCard asset={mockAsset} isEquipped={true} onUnequip={onUnequip} />);

    expect(screen.getByText('Equipped')).toBeDefined();
    const equipBtn = screen.getByTestId('equip-btn-asset-test-wiki-1');
    fireEvent.click(equipBtn);
    expect(onUnequip).toHaveBeenCalledWith(mockAsset);
  });

  it('triggers onOpenAcl when clicking the ACL capsule', () => {
    const onOpenAcl = vi.fn();
    render(<MemoryAssetCard asset={mockAsset} isEquipped={false} onOpenAcl={onOpenAcl} />);

    const aclBtn = screen.getByLabelText('Configure ACL');
    fireEvent.click(aclBtn);
    expect(onOpenAcl).toHaveBeenCalledWith(mockAsset);
  });
});
