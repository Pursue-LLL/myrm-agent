/**
 * Unit tests for AgentEquipmentSlots component.
 *
 * [INPUT] AgentEquipmentSlots, EquipmentSlot
 * [OUTPUT] Full coverage for 4-slot rack rendering, capacity tracking, unequip actions, and empty slot selection.
 * [POS] src/components/features/memory-hub/__tests__/AgentEquipmentSlots.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AgentEquipmentSlots } from '../AgentEquipmentSlots';
import type { EquipmentSlot } from '../memoryHubTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    equipmentLoadout: 'Cognitive Memory Equipment Loadout',
    equipmentSubtitle: 'Mounted memory assets active in the current cognitive loop',
    equippedSlotsCount: 'slots',
    unequip: 'Unequip',
    clickToMount: 'Available for mount',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('AgentEquipmentSlots', () => {
  const mockSlots: EquipmentSlot[] = [
    {
      slot_id: 'slot_chat',
      slot_name: 'Chat Memory Slot',
      allowed_types: ['chat_memory'],
      equipped_asset_id: 'asset-chat-dev-prefs',
      equipped_asset: {
        id: 'asset-chat-dev-prefs',
        name: 'Developer Preferences & Code Style',
        description: 'Long-term user preferences for concise typing.',
        asset_type: 'chat_memory',
        acl_scope: 'team',
        owner_agent_id: 'system',
        project_id: 'default-project',
        allowed_agent_ids: [],
        content_preview: 'Prefers strict typing.',
        tags: ['preferences'],
        size_bytes: 2048,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
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
  ];

  it('renders loadout title and capacity counter correctly', () => {
    render(<AgentEquipmentSlots slots={mockSlots} totalEquipped={1} maxSlots={4} onUnequipSlot={vi.fn()} />);

    expect(screen.getByText('Cognitive Memory Equipment Loadout')).toBeDefined();
    expect(screen.getByText(/1 \/ 4/)).toBeDefined();
  });

  it('renders equipped slot with asset name and triggers onUnequipSlot', () => {
    const onUnequipSlot = vi.fn();
    render(<AgentEquipmentSlots slots={mockSlots} totalEquipped={1} maxSlots={4} onUnequipSlot={onUnequipSlot} />);

    expect(screen.getByTestId('equipped-slot-slot_chat')).toBeDefined();
    expect(screen.getByText('Developer Preferences & Code Style')).toBeDefined();

    const unequipBtn = screen.getByTestId('unequip-btn-slot_chat');
    fireEvent.click(unequipBtn);
    expect(onUnequipSlot).toHaveBeenCalledWith('slot_chat');
  });

  it('renders empty slot and triggers onSelectEmptySlot when clicked', () => {
    const onSelectEmptySlot = vi.fn();
    render(
      <AgentEquipmentSlots
        slots={mockSlots}
        totalEquipped={1}
        maxSlots={4}
        onUnequipSlot={vi.fn()}
        onSelectEmptySlot={onSelectEmptySlot}
      />,
    );

    const emptySkillSlot = screen.getByTestId('empty-slot-slot_skill');
    expect(emptySkillSlot).toBeDefined();

    fireEvent.click(emptySkillSlot);
    expect(onSelectEmptySlot).toHaveBeenCalledWith(mockSlots[1]);
  });
});
