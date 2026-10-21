/**
 * Unit tests for ComposerContextChipStrip.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ComposerContextChipStrip } from '../ComposerContextChipStrip';
import type { ContextChipItem, ComposerContextSummary } from '@/hooks/message-input/useComposerContextChips';

const TRANSLATIONS: Record<string, string> = {
  'chat.contextStrip.remove': 'Remove',
  'chat.contextStrip.removeSkill': 'Remove skill',
  'chat.contextStrip.overloadAria': 'High tool load warning: Click to narrow active capabilities',
  'chat.contextStrip.badgeAria': '{count} active capabilities',
  'chat.contextStrip.capabilities': 'Active',
  'chat.contextStrip.activeCapabilitiesTitle': 'Turn Capability Scope',
  'chat.contextStrip.skillCountDesc': '{count} active skills',
  'chat.contextStrip.mcpCountDesc': '{count} active MCP services',
  'chat.contextStrip.overloadWarning': 'High tool count loaded',
  'chat.contextStrip.moreChipsAria': '{count} more context items',
  'chat.contextStrip.moreContextTitle': 'Mounted Context Items',
  'chat.contextStrip.moreItems': 'View remaining {count} context items',
  'chat.contextStrip.attachedContextTitle': 'Mounted Context',
  'chat.contextStrip.heavyPayload': 'High tool load',
  'chat.contextStrip.activeSummary': '{count} active context items',
};

const stableT = (namespace: string) => (key: string, params?: Record<string, number | string>) => {
  const fullKey = `${namespace}.${key}`;
  let template = TRANSLATIONS[fullKey] || TRANSLATIONS[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(`{${k}}`, String(v));
    }
  }
  return template;
};

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => false,
  useMediaQuery: () => false,
}));

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => stableT(ns),
}));

describe('ComposerContextChipStrip', () => {
  const defaultSummary: ComposerContextSummary = {
    totalItems: 0,
    totalSkills: 0,
    totalMcp: 0,
    totalFiles: 0,
    isOverloaded: false,
  };

  it('renders null when chips array is empty', () => {
    const { container } = render(<ComposerContextChipStrip chips={[]} summary={defaultSummary} />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('composer-context-chip-strip')).toBeNull();
  });

  it('renders chips and handles remove action click', () => {
    const onRemove = vi.fn();
    const chips: ContextChipItem[] = [
      {
        id: 'workflow-tpl',
        category: 'workflow',
        label: 'Data Audit Template',
        iconType: 'workflow',
        isRemovable: true,
        onRemove,
      },
    ];

    render(<ComposerContextChipStrip chips={chips} summary={{ ...defaultSummary, totalItems: 1 }} />);

    expect(screen.getByTestId('composer-context-chip-strip')).toBeInTheDocument();
    expect(screen.getByText('Data Audit Template')).toBeInTheDocument();

    const removeBtn = screen.getByLabelText('Remove: Data Audit Template');
    fireEvent.click(removeBtn);
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it('displays heavy payload warning when summary is overloaded', () => {
    const chips: ContextChipItem[] = [
      {
        id: 'chip-1',
        category: 'capability',
        label: 'Many Capabilities',
        iconType: 'capability',
        isRemovable: false,
      },
    ];

    render(
      <ComposerContextChipStrip
        chips={chips}
        summary={{
          totalItems: 1,
          totalSkills: 5,
          totalMcp: 3,
          totalFiles: 0,
          isOverloaded: true,
        }}
      />,
    );

    expect(screen.getByText('High tool load')).toBeInTheDocument();
  });

  it('supports overflow dropdown trigger when chips count exceeds threshold', () => {
    const chips: ContextChipItem[] = Array.from({ length: 6 }, (_, i) => ({
      id: `chip-${i}`,
      category: 'skill',
      label: `Skill ${i + 1}`,
      iconType: 'skill',
      isRemovable: true,
      onRemove: vi.fn(),
    }));

    render(<ComposerContextChipStrip chips={chips} summary={{ ...defaultSummary, totalItems: 6 }} />);

    // Default desktop maxVisible is 4, so overflow chips count is 2 (+2)
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('triggers onOpenCapabilityEditor when amber overload badge is clicked', () => {
    const onOpenCapabilityEditor = vi.fn();
    const chips: ContextChipItem[] = [
      {
        id: 'chip-1',
        category: 'capability',
        label: 'Loaded MCPs',
        iconType: 'capability',
        isRemovable: false,
      },
    ];

    render(
      <ComposerContextChipStrip
        chips={chips}
        summary={{
          totalItems: 1,
          totalSkills: 5,
          totalMcp: 3,
          totalFiles: 0,
          isOverloaded: true,
        }}
        onOpenCapabilityEditor={onOpenCapabilityEditor}
      />,
    );

    const overloadBtn = screen.getByTestId('composer-overload-nudge');
    expect(overloadBtn).toBeInTheDocument();
    fireEvent.click(overloadBtn);
    expect(onOpenCapabilityEditor).toHaveBeenCalledTimes(1);
  });

  it('triggers chip.onAction when clickable chip is clicked', () => {
    const onAction = vi.fn();
    const chips: ContextChipItem[] = [
      {
        id: 'chip-capability',
        category: 'capability',
        label: 'Configure Scope',
        iconType: 'capability',
        isRemovable: false,
        onAction,
      },
    ];

    render(<ComposerContextChipStrip chips={chips} summary={{ ...defaultSummary, totalItems: 1 }} />);

    const chipEl = screen.getByTestId('context-chip-chip-capability');
    expect(chipEl).toBeInTheDocument();
    fireEvent.click(chipEl);
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
