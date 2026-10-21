import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QuickScratchpadModal } from '../QuickScratchpadModal';
import { useScratchpadStore } from '../useScratchpadStore';

describe('QuickScratchpadModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useScratchpadStore.getState().clearDraft();
    useScratchpadStore.getState().closeScratchpad();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<QuickScratchpadModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal when open and updates draft inputs', () => {
    useScratchpadStore.getState().openScratchpad();
    render(<QuickScratchpadModal />);

    const titleInput = screen.getByPlaceholderText(/titlePlaceholder/i);
    const contentTextarea = screen.getByPlaceholderText(/contentPlaceholder/i);

    expect(titleInput).toBeInTheDocument();
    expect(contentTextarea).toBeInTheDocument();

    fireEvent.change(titleInput, { target: { value: 'Distributed Cache Protocol' } });
    fireEvent.change(contentTextarea, { target: { value: 'Design notes for raft replication.' } });

    const state = useScratchpadStore.getState();
    expect(state.draft.title).toBe('Distributed Cache Protocol');
    expect(state.draft.content).toBe('Design notes for raft replication.');
  });

  it('switches between edit and preview tabs', () => {
    useScratchpadStore.getState().openScratchpad();
    useScratchpadStore.getState().setContent('Markdown body text');
    render(<QuickScratchpadModal />);

    // Click preview tab
    const previewBtn = screen.getByText(/previewTab/i);
    fireEvent.click(previewBtn);

    expect(screen.getByText('Markdown body text')).toBeInTheDocument();

    // Click edit tab
    const editBtn = screen.getByText(/editTab/i);
    fireEvent.click(editBtn);

    expect(screen.getByPlaceholderText(/contentPlaceholder/i)).toBeInTheDocument();
  });

  it('clears draft when trash icon is clicked', () => {
    useScratchpadStore.getState().openScratchpad();
    useScratchpadStore.getState().setTitle('Note to delete');
    render(<QuickScratchpadModal />);

    const clearBtn = screen.getByTitle(/clearDraft/i);
    fireEvent.click(clearBtn);

    expect(useScratchpadStore.getState().draft.title).toBe('');
  });

  it('handles promote confirmation flow', async () => {
    useScratchpadStore.getState().openScratchpad();
    useScratchpadStore.getState().setTitle('Agent Runtime V2');
    useScratchpadStore.getState().setContent('Core runtime loops and scheduler drafts.');

    const mockResponse = {
      project_name: 'agent-runtime-v2',
      target_directory: '/workspaces/agent-runtime-v2',
      created_files: ['docs/scratchpad_origin.md', 'README.md'],
      initial_context_prompt: '<promoted_project>',
      promoted_at: '2026-10-12T19:00:00Z',
      provenance_metadata: {},
    };

    vi.spyOn(window, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    render(<QuickScratchpadModal />);

    const promoteTriggerBtn = screen.getByText(/promoteButton/i);
    fireEvent.click(promoteTriggerBtn);

    const confirmBtn = screen.getByText(/confirmPromote/i);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(useScratchpadStore.getState().promotionResult).toEqual(mockResponse);
    });

    expect(screen.getByText(/promotedSuccess/i)).toBeInTheDocument();
  });
});
