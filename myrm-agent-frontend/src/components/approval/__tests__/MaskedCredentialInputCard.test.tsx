import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MaskedCredentialInputCard } from '../MaskedCredentialInputCard';

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

describe('MaskedCredentialInputCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly with default single-use badge and inputs', () => {
    const handleStagedChange = vi.fn();
    render(
      <MaskedCredentialInputCard
        approvalId="app_test_123"
        stagedHandles={[]}
        onStagedChange={handleStagedChange}
      />,
    );

    expect(screen.getByText('Ephemeral Credentials & Single-Use Gate')).toBeDefined();
    expect(screen.getByText('Zero-Disk / Auto-Wipe')).toBeDefined();
    expect(screen.getByText('Single-use ticket enforced')).toBeDefined();
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
    expect(screen.getByPlaceholderText('••••••••••••')).toBeDefined();
  });

  it('toggles password visibility between masked and text', () => {
    render(
      <MaskedCredentialInputCard
        approvalId="app_test_123"
        stagedHandles={[]}
        onStagedChange={vi.fn()}
      />,
    );

    const secretInput = screen.getByPlaceholderText('••••••••••••') as HTMLInputElement;
    expect(secretInput.type).toBe('password');

    // Click toggle eye button
    const toggleButton = secretInput.nextElementSibling as HTMLButtonElement;
    expect(toggleButton).toBeDefined();
    fireEvent.click(toggleButton);

    expect(secretInput.type).toBe('text');
  });

  it('validates and blocks dangerous system environment variables', () => {
    render(
      <MaskedCredentialInputCard
        approvalId="app_test_123"
        stagedHandles={[]}
        onStagedChange={vi.fn()}
      />,
    );

    const keyInput = screen.getByPlaceholderText('API_SECRET_KEY') as HTMLInputElement;
    fireEvent.change(keyInput, { target: { value: 'PATH' } });

    expect(
      screen.getByText('"PATH" is a protected system environment variable and is blocked'),
    ).toBeDefined();
  });

  it('stages credentials securely via API and updates staged summaries', async () => {
    const handleStagedChange = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        approval_id: 'app_test_123',
        session_id: 'chat_test',
        staged: [
          {
            handle_id: 'cred_ephemeral_xyz123abc456',
            key: 'TEST_API_KEY',
            single_use: true,
            expires_at: Date.now() + 60000,
          },
        ],
      }),
    });

    render(
      <MaskedCredentialInputCard
        approvalId="app_test_123"
        stagedHandles={[]}
        onStagedChange={handleStagedChange}
      />,
    );

    const keyInput = screen.getByPlaceholderText('API_SECRET_KEY');
    const secretInput = screen.getByPlaceholderText('••••••••••••');

    fireEvent.change(keyInput, { target: { value: 'TEST_API_KEY' } });
    fireEvent.change(secretInput, { target: { value: 'super-sensitive-secret-token' } });

    const stageButton = screen.getByText('Stage Masked Credentials');
    fireEvent.click(stageButton);

    await waitFor(() => {
      expect(handleStagedChange).toHaveBeenCalledWith(['cred_ephemeral_xyz123abc456']);
    });

    expect(screen.getByText('Credentials Staged Ready for Execution')).toBeDefined();
    expect(screen.getByText('TEST_API_KEY')).toBeDefined();

    // Revoke clears state
    const revokeButton = screen.getByText('Revoke');
    fireEvent.click(revokeButton);

    expect(handleStagedChange).toHaveBeenCalledWith([]);
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
  });

  it('prefills single suggested key and renders clickable chips for multiple suggested keys', () => {
    // 1. Single suggested key prefilled
    const { unmount } = render(
      <MaskedCredentialInputCard
        approvalId="app_test_1"
        stagedHandles={[]}
        onStagedChange={vi.fn()}
        suggestedKeys={['PGPASSWORD']}
      />,
    );

    const keyInput = screen.getByPlaceholderText('API_SECRET_KEY') as HTMLInputElement;
    expect(keyInput.value).toBe('PGPASSWORD');
    unmount();

    // 2. Multiple suggested keys render chips and click to fill
    render(
      <MaskedCredentialInputCard
        approvalId="app_test_2"
        stagedHandles={[]}
        onStagedChange={vi.fn()}
        suggestedKeys={['DB_HOST_PASSWORD', 'AWS_SECRET_ACCESS_KEY']}
      />,
    );

    expect(screen.getByText('Suggested:')).toBeDefined();
    expect(screen.getByText('DB_HOST_PASSWORD')).toBeDefined();
    const awsChip = screen.getByText('AWS_SECRET_ACCESS_KEY');
    expect(awsChip).toBeDefined();

    // Clicking the chip should add or populate key
    fireEvent.click(awsChip);
    const inputs = screen.getAllByPlaceholderText('API_SECRET_KEY') as HTMLInputElement[];
    expect(inputs.some((input) => input.value === 'AWS_SECRET_ACCESS_KEY')).toBe(true);
  });
});
