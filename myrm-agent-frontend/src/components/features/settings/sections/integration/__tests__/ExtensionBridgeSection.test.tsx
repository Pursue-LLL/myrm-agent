/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { toast } from '@/hooks/shared/useToast';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  createExtensionPairing,
  disconnectExtension,
  getExtensionSetupHints,
  getExtensionStatus,
  updateExtensionAccessPolicy,
  type ExtensionAccessPolicy,
  type ExtensionSetupHints,
  type ExtensionStatus,
} from '@/services/extension';

import ExtensionBridgeSection from '../ExtensionBridgeSection';

// 翻译函数必须是稳定引用：每次渲染都新建会让依赖它的 hook 反复重建。
const { translate } = vi.hoisted(() => ({
  translate: (key: string, params?: Record<string, string | number>) =>
    params ? `${key}|${Object.values(params).join(',')}` : key,
}));

vi.mock('next-intl', () => ({ useTranslations: () => translate }));

vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));
vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard: vi.fn() }));
vi.mock('../extension/ExtensionClipAgentField', () => ({ default: () => null }));
vi.mock('@/services/extension', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/extension')>()),
  getExtensionStatus: vi.fn(),
  getExtensionSetupHints: vi.fn(),
  getExtensionWebSocketUrl: () => 'ws://localhost:8080/api/v1/ws/extension',
  updateExtensionAccessPolicy: vi.fn(),
  disconnectExtension: vi.fn(),
  createExtensionPairing: vi.fn(),
}));

const CONNECTED: ExtensionStatus = {
  connected: true,
  handshake_ready: true,
  relay_cdp_ready: true,
  extension_version: '1.2.3',
  browser_name: 'Chrome',
  authorized_domains: ['a.com'],
  allow_all_eligible_tabs: false,
  paused_tab_ids: [],
  access_policy_valid: true,
  capabilities: ['navigate_url', 'list_tabs', 'attach_debugger', 'detach_debugger'],
  available_tabs: [{ tab_id: 7, url: 'https://a.com/x', title: 'A page', domain: 'a.com', active: true }],
};
const HINTS: ExtensionSetupHints = {
  auth_token_configured: true,
  auth_token_required: false,
  cdp_endpoint_discovered: false,
  relay_cdp_ready: true,
  access_policy_valid: true,
};
const SAVED: ExtensionAccessPolicy = {
  allow_all_eligible_tabs: false,
  authorized_domains: ['a.com', 'b.com'],
  paused_tab_ids: [],
  policy_valid: true,
  warnings: [],
};

beforeEach(() => {
  vi.mocked(getExtensionStatus).mockResolvedValue(CONNECTED);
  vi.mocked(getExtensionSetupHints).mockResolvedValue(HINTS);
  vi.mocked(updateExtensionAccessPolicy).mockResolvedValue(SAVED);
  vi.mocked(disconnectExtension).mockResolvedValue(undefined);
  vi.mocked(writeToClipboard).mockResolvedValue(true);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ExtensionBridgeSection', () => {
  it('shows the connection, authorized domains and open tabs of a connected extension', async () => {
    render(<ExtensionBridgeSection />);

    expect(await screen.findByText('Chrome · v1.2.3')).toBeInTheDocument();
    expect(screen.getByText('a.com', { selector: '.font-mono' })).toBeInTheDocument();
    expect(screen.getByText('extension.tabPause')).toBeInTheDocument();
    expect(screen.queryByText('extension.setupGuide')).not.toBeInTheDocument();
  });

  it('shows the setup guide and no tab list while disconnected', async () => {
    vi.mocked(getExtensionStatus).mockResolvedValue({ ...CONNECTED, connected: false, available_tabs: [] });

    render(<ExtensionBridgeSection />);

    expect(await screen.findByText('extension.setupGuide')).toBeInTheDocument();
    expect(screen.queryByText('extension.availableTabs')).not.toBeInTheDocument();
  });

  it('adds a domain, clears the input and confirms with a toast', async () => {
    render(<ExtensionBridgeSection />);

    const input = await screen.findByPlaceholderText('extension.domainPlaceholder');
    fireEvent.change(input, { target: { value: ' b.com ' } });
    fireEvent.click(screen.getByText('extension.addDomain'));

    await waitFor(() =>
      expect(updateExtensionAccessPolicy).toHaveBeenCalledWith({
        allow_all_eligible_tabs: false,
        domains: ['a.com', 'b.com'],
        paused_tab_ids: [],
      }),
    );
    expect(await screen.findByText('b.com')).toBeInTheDocument();
    expect(input).toHaveValue('');
    expect(toast).toHaveBeenCalledWith({ title: 'extension.domainAdded', variant: 'default' });
  });

  it('warns when a wildcard domain also covers its root domain', async () => {
    vi.mocked(updateExtensionAccessPolicy).mockResolvedValue({
      ...SAVED,
      warnings: [{ code: 'wildcard_includes_root', pattern: '*.b.com', root_domain: 'b.com' }],
    });

    render(<ExtensionBridgeSection />);

    fireEvent.change(await screen.findByPlaceholderText('extension.domainPlaceholder'), {
      target: { value: '*.b.com' },
    });
    fireEvent.click(screen.getByText('extension.addDomain'));

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: 'extension.wildcardWarningTitle',
        description: 'extension.wildcardIncludesRoot|*.b.com,b.com',
        variant: 'default',
      }),
    );
  });

  it('removes a domain without the add confirmation', async () => {
    vi.mocked(updateExtensionAccessPolicy).mockResolvedValue({ ...SAVED, authorized_domains: [] });

    render(<ExtensionBridgeSection />);

    const chip = await screen.findByText('a.com', { selector: 'div' });
    fireEvent.click(within(chip).getByRole('button'));

    await waitFor(() =>
      expect(updateExtensionAccessPolicy).toHaveBeenCalledWith({
        allow_all_eligible_tabs: false,
        domains: [],
        paused_tab_ids: [],
      }),
    );
    expect(toast).not.toHaveBeenCalled();
  });

  it('toggles allow-all for eligible tabs', async () => {
    vi.mocked(updateExtensionAccessPolicy).mockResolvedValue({ ...SAVED, allow_all_eligible_tabs: true });

    render(<ExtensionBridgeSection />);

    fireEvent.click(await screen.findByRole('switch'));

    await waitFor(() =>
      expect(updateExtensionAccessPolicy).toHaveBeenCalledWith({
        allow_all_eligible_tabs: true,
        domains: ['a.com'],
        paused_tab_ids: [],
      }),
    );
  });

  it('pauses a tab and then refreshes the status', async () => {
    vi.mocked(updateExtensionAccessPolicy).mockResolvedValue({ ...SAVED, paused_tab_ids: [7] });

    render(<ExtensionBridgeSection />);

    await screen.findByText('extension.tabPause');
    const statusCalls = vi.mocked(getExtensionStatus).mock.calls.length;
    fireEvent.click(screen.getByText('extension.tabPause'));

    await waitFor(() =>
      expect(updateExtensionAccessPolicy).toHaveBeenCalledWith({
        allow_all_eligible_tabs: false,
        domains: ['a.com'],
        paused_tab_ids: [7],
      }),
    );
    await waitFor(() => expect(vi.mocked(getExtensionStatus).mock.calls.length).toBeGreaterThan(statusCalls));
  });

  it('reports a failed policy save and re-enables editing', async () => {
    vi.mocked(updateExtensionAccessPolicy).mockRejectedValue(new Error('denied'));

    render(<ExtensionBridgeSection />);

    fireEvent.change(await screen.findByPlaceholderText('extension.domainPlaceholder'), { target: { value: 'b.com' } });
    fireEvent.click(screen.getByText('extension.addDomain'));

    await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: 'extension.saveFailed', variant: 'destructive' }));
    await waitFor(() => expect(screen.getByText('extension.addDomain').closest('button')).not.toBeDisabled());
    expect(toast).not.toHaveBeenCalledWith({ title: 'extension.domainAdded', variant: 'default' });
  });

  it('disconnects the extension', async () => {
    render(<ExtensionBridgeSection />);

    fireEvent.click(await screen.findByText('extension.disconnect'));

    await waitFor(() => expect(disconnectExtension).toHaveBeenCalledOnce());
    await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: 'extension.disconnected', variant: 'default' }));
  });

  it('creates a pairing code and copies the pairing bundle', async () => {
    vi.mocked(createExtensionPairing).mockResolvedValue({
      code: 'PAIR-1',
      expires_in: 60,
      ws_url: 'ws://x',
      http_base: 'http://localhost:8080',
      consume_url: 'http://x/consume',
    });

    render(<ExtensionBridgeSection />);

    fireEvent.click(await screen.findByText('extension.createPairingCode'));

    expect(await screen.findByText('PAIR-1')).toBeInTheDocument();
    expect(writeToClipboard).toHaveBeenCalledWith(
      JSON.stringify({ http_base: 'http://localhost:8080', code: 'PAIR-1' }),
      true,
    );
    expect(toast).toHaveBeenCalledWith({ title: 'extension.pairingCopied', variant: 'default' });
  });

  it('shows the fetch error with the destructive text token and retries', async () => {
    vi.mocked(getExtensionStatus).mockRejectedValueOnce(new Error('offline'));

    render(<ExtensionBridgeSection />);

    const message = await screen.findByText('extension.fetchError');
    expect(message.closest('p')).toHaveClass('text-destructive-text');

    fireEvent.click(screen.getByText('extension.retry'));

    expect(await screen.findByText('Chrome · v1.2.3')).toBeInTheDocument();
    expect(screen.queryByText('extension.fetchError')).not.toBeInTheDocument();
  });

  it('flags a missing auth token and an invalid access policy with the destructive text token', async () => {
    vi.mocked(getExtensionSetupHints).mockResolvedValue({
      ...HINTS,
      auth_token_configured: false,
      auth_token_required: true,
    });
    vi.mocked(getExtensionStatus).mockResolvedValue({ ...CONNECTED, access_policy_valid: false });

    render(<ExtensionBridgeSection />);

    expect(await screen.findByText('extension.authTokenRequiredHelp')).toHaveClass('text-destructive-text');
    expect(screen.getByText('extension.accessPolicyInvalidHelp')).toHaveClass('text-destructive-text');
  });
});
