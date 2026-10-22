/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ComposerMentionDropdown } from '../ComposerMentionDropdown';
import { GroupParticipant } from '../groupChatTypes';

const mockParticipants: GroupParticipant[] = [
  {
    participant_id: 'user_me',
    name: 'You (Operator)',
    role: 'human',
    avatar_seed: 'user_me',
    avatar_color: '#0f172a',
    is_avatar_locked: true,
  },
  {
    participant_id: 'code_architect',
    name: 'Code Architect',
    role: 'assistant_bot',
    avatar_seed: 'code_architect',
    avatar_color: '#6366f1',
    is_avatar_locked: true,
    description: 'System design specialist',
  },
  {
    participant_id: 'test_runner',
    name: 'Test Runner',
    role: 'assistant_bot',
    avatar_seed: 'test_runner',
    avatar_color: '#10b981',
    is_avatar_locked: true,
    description: 'Automated test suite validator',
  },
];

describe('ComposerMentionDropdown', () => {
  it('renders null when isOpen is false', () => {
    const { container } = render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query=""
        isOpen={false}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders only assistant bots when open', () => {
    render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query=""
        isOpen={true}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('@Code Architect')).toBeInTheDocument();
    expect(screen.getByText('@Test Runner')).toBeInTheDocument();
    expect(screen.queryByText('@You (Operator)')).not.toBeInTheDocument();
  });

  it('filters candidates based on query', () => {
    render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query="test"
        isOpen={true}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('@Test Runner')).toBeInTheDocument();
    expect(screen.queryByText('@Code Architect')).not.toBeInTheDocument();
  });

  it('triggers onSelect when an option is clicked', () => {
    const handleSelect = vi.fn();
    render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query=""
        isOpen={true}
        onSelect={handleSelect}
        onClose={vi.fn()}
      />
    );

    const architectOption = screen.getByText('@Code Architect');
    fireEvent.click(architectOption);

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(handleSelect).toHaveBeenCalledWith(
      expect.objectContaining({ participant_id: 'code_architect' })
    );
  });

  it('supports keyboard navigation with arrow keys and Enter', () => {
    const handleSelect = vi.fn();
    render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query=""
        isOpen={true}
        onSelect={handleSelect}
        onClose={vi.fn()}
      />
    );

    // Arrow down moves to test_runner
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    // Press Enter to select
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(handleSelect).toHaveBeenCalledWith(
      expect.objectContaining({ participant_id: 'test_runner' })
    );
  });

  it('calls onClose when Escape key is pressed', () => {
    const handleClose = vi.fn();
    render(
      <ComposerMentionDropdown
        participants={mockParticipants}
        query=""
        isOpen={true}
        onSelect={vi.fn()}
        onClose={handleClose}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
