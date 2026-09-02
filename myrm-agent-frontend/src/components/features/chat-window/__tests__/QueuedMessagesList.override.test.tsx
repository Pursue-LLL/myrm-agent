/**
 * Unit tests for QueuedMessagesList turn capability override badge.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { QueuedMessagesList } from '../QueuedMessagesList';

const CHAT_T: Record<string, string> = {
  'queue.queued': 'Queued #{index}/{total}:',
  'queue.edit': 'Edit',
  'queue.cancel': 'Cancel',
  'queue.saveEdit': 'Save',
  'queue.cancelEdit': 'Cancel',
  overrideSkillsShort: '{skills} skills',
  overrideMcpShort: '{mcps} MCP',
};

const stableT = (key: string, params?: Record<string, number | string>) => {
  let template = CHAT_T[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(`{${k}}`, String(v));
    }
  }
  return template;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('QueuedMessagesList override badge', () => {
  it('renders override badge when queued message has turnCapabilitySelection', () => {
    const queue = [
      {
        id: 'q-1',
        text: 'Task with override',
        turnCapabilitySelection: {
          skillIds: ['skill-1', 'skill-2'],
          mcpNames: ['mcp-1'],
        },
      },
      {
        id: 'q-2',
        text: 'Normal queued task',
        turnCapabilitySelection: null,
      },
    ];

    render(
      <QueuedMessagesList
        queue={queue}
        editMessage={vi.fn()}
        removeMessage={vi.fn()}
        reorder={vi.fn()}
      />,
    );

    expect(screen.getByText('2 skills · 1 MCP')).toBeInTheDocument();
    expect(screen.getByText('Task with override')).toBeInTheDocument();
    expect(screen.getByText('Normal queued task')).toBeInTheDocument();
  });
});
