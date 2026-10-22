import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LightweightFusenBoardCard } from '../LightweightFusenBoardCard';

describe('LightweightFusenBoardCard', () => {
  it('renders fusen board header, session id, and active blocker indicator', () => {
    const handleDismiss = vi.fn();
    render(
      <LightweightFusenBoardCard
        sessionId="sess-test-fusen"
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByRole('region', {
        name: /Lightweight Fusen Shared State Board/i,
      })
    ).toBeInTheDocument();
    expect(screen.getByText('Fusen Shared State Board')).toBeInTheDocument();
    expect(screen.getByText('sess-test-fusen')).toBeInTheDocument();

    // Verify initial blocker indicator
    expect(screen.getByText('1 Active Blocker')).toBeInTheDocument();

    // Verify initial sticky notes
    expect(screen.getByText('blocked_by: migration_lock')).toBeInTheDocument();
    expect(screen.getByText('ready_for_review: diff_jwt_service')).toBeInTheDocument();
    expect(screen.getByText('cache_hit: turborepo_artifacts')).toBeInTheDocument();

    // Test dismiss button
    const closeBtn = screen.getByLabelText('Close Fusen board');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('filters notes by category', () => {
    render(<LightweightFusenBoardCard />);

    // Filter by cache_hint
    const cacheFilterBtn = screen.getByRole('button', { name: /^cache hint$/i });
    fireEvent.click(cacheFilterBtn);

    expect(screen.getByText('cache_hit: turborepo_artifacts')).toBeInTheDocument();
    expect(screen.queryByText('blocked_by: migration_lock')).not.toBeInTheDocument();

    // Reset to all
    const allFilterBtn = screen.getByRole('button', { name: /^all$/i });
    fireEvent.click(allFilterBtn);

    expect(screen.getByText('blocked_by: migration_lock')).toBeInTheDocument();
  });

  it('resolves active note with resolution input', () => {
    const handleResolve = vi.fn();
    render(<LightweightFusenBoardCard onNoteResolved={handleResolve} />);

    // Find Resolve buttons
    const resolveButtons = screen.getAllByRole('button', { name: /Resolve/i });
    expect(resolveButtons.length).toBeGreaterThan(0);

    // Click Resolve on the first note
    fireEvent.click(resolveButtons[0]);

    // Input resolution note
    const input = screen.getByPlaceholderText('Resolution note...');
    fireEvent.change(input, { target: { value: 'Applied migration index successfully.' } });

    // Confirm resolve
    const confirmBtn = screen.getByLabelText('Confirm resolve');
    fireEvent.click(confirmBtn);

    expect(handleResolve).toHaveBeenCalledWith('fusen-blk-01');

    // Blocker cleared: now Swarm Clear
    expect(screen.getByText('Swarm Clear')).toBeInTheDocument();
  });

  it('posts new sticky note via modal dialog', () => {
    const handlePosted = vi.fn();
    render(<LightweightFusenBoardCard onNotePosted={handlePosted} />);

    // Click Post Fusen button
    const postBtn = screen.getByRole('button', { name: /Post Fusen/i });
    fireEvent.click(postBtn);

    // Modal appears
    expect(screen.getByText('Post Lightweight Fusen Sticky Note')).toBeInTheDocument();

    // Fill form
    const tagInput = screen.getByPlaceholderText(/e\.g\. blocked_by: api_gateway_503/i);
    fireEvent.change(tagInput, { target: { value: 'blocked_by: redis_timeout' } });

    const contentInput = screen.getByPlaceholderText(/Provide minimal micro-context/i);
    fireEvent.change(contentInput, { target: { value: 'Redis cache node unresponsive.' } });

    // Submit form
    const submitBtn = screen.getByRole('button', { name: 'Post Sticky Note' });
    fireEvent.click(submitBtn);

    // Verify new note is on the wall
    expect(screen.getByText('blocked_by: redis_timeout')).toBeInTheDocument();
    expect(screen.getByText('Redis cache node unresponsive.')).toBeInTheDocument();
    expect(handlePosted).toHaveBeenCalledTimes(1);
  });
});
