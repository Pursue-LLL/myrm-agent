import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VirtualRoomCoDevCockpitCard } from '../VirtualRoomCoDevCockpitCard';

describe('VirtualRoomCoDevCockpitCard', () => {
  it('renders room header, default locks tab and initial locks correctly', () => {
    const handleDismiss = vi.fn();
    render(
      <VirtualRoomCoDevCockpitCard
        roomId="room-test-101"
        roomName="Alpha Co-Dev Space"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByRole('region', { name: /Virtual Room Co-Dev Cockpit/i })).toBeInTheDocument();
    expect(screen.getByText('Alpha Co-Dev Space')).toBeInTheDocument();
    expect(screen.getByText('LIVE ROOM')).toBeInTheDocument();
    expect(screen.getByText(/ID: room-test-101/i)).toBeInTheDocument();

    // Default tab is locks
    expect(screen.getByText(/src\/services\/payment.ts/i)).toBeInTheDocument();
    expect(screen.getByText(/\[Lines 45-92\]/i)).toBeInTheDocument();
    expect(screen.getByText(/src\/auth\/jwt.ts/i)).toBeInTheDocument();
    expect(screen.getByText(/\[FULL FILE\]/i)).toBeInTheDocument();

    // Dismiss button
    const closeBtn = screen.getByLabelText('Close Room Cockpit');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches tabs to roster, borrowing, and preview', () => {
    render(<VirtualRoomCoDevCockpitCard />);

    // Switch to Roster
    const rosterTabBtn = screen.getByText(/Roster/i);
    fireEvent.click(rosterTabBtn);
    expect(screen.getByText('Alice (Architect)')).toBeInTheDocument();
    expect(screen.getByText('CodeCraft (Local)')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek-V3 Auditor')).toBeInTheDocument();
    expect(screen.getByText(/Editing: src\/core\/vfs.rs/i)).toBeInTheDocument();

    // Switch to Agent Borrowing
    const borrowingTabBtn = screen.getByText(/Agent Borrowing/i);
    fireEvent.click(borrowingTabBtn);
    expect(screen.getByText(/Zero-Credential Safe Delegation Gateway/i)).toBeInTheDocument();
    expect(screen.getByText(/Bob \(Peer Human\) → Borrower: Alice \(Architect\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Tokens: 14,200 \/ 50,000/i)).toBeInTheDocument();

    // Switch to Live Previews
    const previewTabBtn = screen.getByText(/Live Previews/i);
    fireEvent.click(previewTabBtn);
    expect(screen.getByText('Next.js App Preview')).toBeInTheDocument();
    expect(screen.getByText(':3000')).toBeInTheDocument();
    expect(screen.getByText('FastAPI Microservice')).toBeInTheDocument();
    expect(screen.getByText(':8000')).toBeInTheDocument();
  });

  it('allows acquiring a safe range lock and releasing locks', () => {
    const handleLockAcquired = vi.fn();
    render(<VirtualRoomCoDevCockpitCard onLockAcquired={handleLockAcquired} />);

    // Initially 2 locks
    expect(screen.getByText('VFS Line Locks (2)')).toBeInTheDocument();

    // Acquire safe range lock
    const acquireBtn = screen.getByText('Acquire Safe Range Lock');
    fireEvent.click(acquireBtn);

    expect(handleLockAcquired).toHaveBeenCalledTimes(1);
    expect(screen.getByText('VFS Line Locks (3)')).toBeInTheDocument();
    expect(screen.getByText(/\[Lines 120-160\]/i)).toBeInTheDocument();

    // Release the first lock
    const releaseBtn = screen.getByLabelText('Release lock lock-vfs-01');
    fireEvent.click(releaseBtn);

    expect(screen.queryByText(/\[Lines 45-92\]/i)).not.toBeInTheDocument();
    expect(screen.getByText('VFS Line Locks (2)')).toBeInTheDocument();
  });

  it('revokes an active agent borrowing grant', () => {
    render(<VirtualRoomCoDevCockpitCard />);

    const borrowingTabBtn = screen.getByText(/Agent Borrowing/i);
    fireEvent.click(borrowingTabBtn);

    const revokeBtn = screen.getByText('Revoke Grant');
    fireEvent.click(revokeBtn);

    expect(screen.getByText('revoked')).toBeInTheDocument();
    expect(screen.queryByText('Revoke Grant')).not.toBeInTheDocument();
  });
});
