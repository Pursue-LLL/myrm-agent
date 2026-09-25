import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
  TaintedEgressApprovalModal,
  type TaintedEgressApprovalItem,
} from '../TaintedEgressApprovalModal';

describe('TaintedEgressApprovalModal', () => {
  const mockItem: TaintedEgressApprovalItem = {
    requestId: 'req-test-123',
    destinationHost: 'api.github.com',
    destinationPort: 443,
    sensitiveDataType: 'github_token',
    detectedPattern: 'ghp_[0-9a-zA-Z]{36}',
    sessionId: 'session-alpha',
  };

  const onApprove = vi.fn();
  const onReject = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <TaintedEgressApprovalModal
        isOpen={false}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when item is null', () => {
    const { container } = render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={null}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders details correctly when open with an item', () => {
    render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/api.github.com:443/)).toBeInTheDocument();
    expect(screen.getByText('github_token')).toBeInTheDocument();
    expect(screen.getByText('ghp_[0-9a-zA-Z]{36}')).toBeInTheDocument();
  });

  it('calls onApprove with trustSession=false by default', async () => {
    onApprove.mockResolvedValueOnce(undefined);

    render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(onApprove).toHaveBeenCalledWith('req-test-123', 'api.github.com', false);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls onApprove with trustSession=true when checkbox is toggled', async () => {
    onApprove.mockResolvedValueOnce(undefined);

    render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(onApprove).toHaveBeenCalledWith('req-test-123', 'api.github.com', true);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls onReject when reject button is clicked', async () => {
    onReject.mockResolvedValueOnce(undefined);

    render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );

    const rejectBtn = screen.getByRole('button', { name: /reject/i });
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(onReject).toHaveBeenCalledWith('req-test-123', 'user_declined');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls onClose when close button is clicked', () => {
    render(
      <TaintedEgressApprovalModal
        isOpen={true}
        item={mockItem}
        onApprove={onApprove}
        onReject={onReject}
        onClose={onClose}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
