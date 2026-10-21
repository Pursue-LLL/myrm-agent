import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MaskedCredentialInputCard } from '../MaskedCredentialInputCard';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

describe('MaskedCredentialInputCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly with default single-use badge and inputs', () => {
    const handleStagedChange = vi.fn();
    render(
      <MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={handleStagedChange} />,
    );

    expect(screen.getByText('title')).toBeDefined();
    expect(screen.getByText('badgeZeroDisk')).toBeDefined();
    expect(screen.getByText('singleUseEnforced')).toBeDefined();
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
    expect(screen.getByPlaceholderText('••••••••••••')).toBeDefined();
  });

  it('toggles password visibility between masked and text', () => {
    render(<MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={vi.fn()} />);

    const secretInput = screen.getByPlaceholderText('••••••••••••') as HTMLInputElement;
    expect(secretInput.type).toBe('password');

    // Click toggle eye button
    const toggleButton = screen.getByRole('button', { name: 'showSecret' });
    expect(toggleButton).toBe(secretInput.nextElementSibling);
    fireEvent.click(toggleButton);

    expect(secretInput.type).toBe('text');
    expect(screen.getByRole('button', { name: 'hideSecret' })).toBe(toggleButton);
  });

  it('validates and blocks dangerous system environment variables', () => {
    render(<MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={vi.fn()} />);

    const keyInput = screen.getByPlaceholderText('API_SECRET_KEY') as HTMLInputElement;
    fireEvent.change(keyInput, { target: { value: 'PATH' } });

    expect(screen.getByText('keyErrorBlocked:{"key":"PATH"}')).toBeDefined();
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
      <MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={handleStagedChange} />,
    );

    const keyInput = screen.getByPlaceholderText('API_SECRET_KEY');
    const secretInput = screen.getByPlaceholderText('••••••••••••');

    fireEvent.change(keyInput, { target: { value: 'TEST_API_KEY' } });
    fireEvent.change(secretInput, { target: { value: 'super-sensitive-secret-token' } });

    const stageButton = screen.getByText('stage');
    fireEvent.click(stageButton);

    await waitFor(() => {
      expect(handleStagedChange).toHaveBeenCalledWith(['cred_ephemeral_xyz123abc456']);
    });

    expect(screen.getByText('stagedReady')).toBeDefined();
    expect(screen.getByText('TEST_API_KEY')).toBeDefined();

    // Revoke clears state
    const revokeButton = screen.getByText('revoke');
    fireEvent.click(revokeButton);

    expect(handleStagedChange).toHaveBeenCalledWith([]);
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
    expect(toastMock.success).toHaveBeenCalledWith('toastStaged');
    expect(toastMock.info).toHaveBeenCalledWith('toastCleared');
  });

  it('surfaces the server detail through the translated failure toast and keeps the drafts', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'approval expired' }),
    });
    const handleStagedChange = vi.fn();

    render(
      <MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={handleStagedChange} />,
    );

    fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'TEST_API_KEY' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith('toastStageFailed:{"message":"approval expired"}');
    });
    expect(handleStagedChange).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
  });

  it('falls back to the translated status message when the server gives no detail', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => {
        throw new Error('not json');
      },
    });

    render(<MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'TEST_API_KEY' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining('errorServerStatus'));
    });
  });

  it('blocks staging with a translated toast when a protected key is entered', () => {
    render(<MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'path' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByText('stage'));

    expect(toastMock.error).toHaveBeenCalledWith('keyErrorBlocked:{"key":"PATH"}');
  });

  it('lets users remove an extra credential row through a labelled control', () => {
    render(<MaskedCredentialInputCard approvalId="app_test_123" stagedHandles={[]} onStagedChange={vi.fn()} />);

    fireEvent.click(screen.getByText('addRow'));
    expect(screen.getAllByPlaceholderText('API_SECRET_KEY')).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('button', { name: 'removeCredential' })[0]);

    expect(screen.getAllByPlaceholderText('API_SECRET_KEY')).toHaveLength(1);
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

    expect(screen.getByText('suggested')).toBeDefined();
    expect(screen.getByText('DB_HOST_PASSWORD')).toBeDefined();
    const awsChip = screen.getByText('AWS_SECRET_ACCESS_KEY');
    expect(awsChip).toBeDefined();

    // Clicking the chip should add or populate key
    fireEvent.click(awsChip);
    const inputs = screen.getAllByPlaceholderText('API_SECRET_KEY') as HTMLInputElement[];
    expect(inputs.some((input) => input.value === 'AWS_SECRET_ACCESS_KEY')).toBe(true);
  });
});
