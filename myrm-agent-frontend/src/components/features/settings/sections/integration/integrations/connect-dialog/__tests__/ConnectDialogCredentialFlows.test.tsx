/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import {
  GATE_ALLOWED,
  makeEntry,
  makeStoredConfig,
  mockApiRequest,
  mockGateMcpEnable,
  mockSetMCPConfigs,
  mockToast,
  resetConnectDialogMocks,
  SCAN_SUMMARY,
  storeState,
} from './connectDialogTestKit';

vi.mock('next-intl', async () => (await import('./connectDialogTestKit')).nextIntlMock);
vi.mock('@/hooks/shared/useToast', async () => (await import('./connectDialogTestKit')).toastMock);
vi.mock('@/store/useConfigStore', async () => (await import('./connectDialogTestKit')).configStoreMock);
vi.mock('@/lib/api', async () => (await import('./connectDialogTestKit')).apiMock);
vi.mock('@/hooks/settings/useMcpSecurityGate', async () => (await import('./connectDialogTestKit')).securityGateMock);
vi.mock('@/lib/utils/mcp-config', async () => (await import('./connectDialogTestKit')).mcpConfigUtilsMock);
vi.mock(
  '@/components/features/settings/mcp/MCPScanAckDialog',
  async () => (await import('./connectDialogTestKit')).scanAckDialogMock,
);
vi.mock('@/lib/deploy-mode', async () => (await import('./connectDialogTestKit')).deployModeMock);

import type { CatalogLocale } from '../../catalog-locale';
import type { CatalogEntry } from '../../catalog-types';
import { IntegrationConnectDialog } from '../../IntegrationConnectDialog';

function renderDialog(entry: CatalogEntry, locale: CatalogLocale = 'en') {
  const onClose = vi.fn();
  const onConnected = vi.fn();
  render(<IntegrationConnectDialog entry={entry} locale={locale} onClose={onClose} onConnected={onConnected} />);
  return { onClose, onConnected };
}

function clickConnect() {
  fireEvent.click(screen.getByRole('button', { name: 'connect' }));
}

const multiFieldEntry = (overrides?: Partial<CatalogEntry>) =>
  makeEntry({
    envKey: null,
    credentialFields: [
      { key: 'API_KEY', label: 'API Key', labelZh: '密钥', inject: 'env' },
      { key: 'X-Auth', label: 'Auth Header', labelZh: '认证头', inject: 'header' },
      { key: '{{PROJECT}}', label: 'Project', labelZh: '项目', inject: 'arg_placeholder' },
    ],
    mcpConfig: {
      name: 'svc',
      type: 'stdio',
      command: 'run',
      args: ['--project', '{{PROJECT}}'],
      env: { BASE: '1' },
      headers: { 'X-Static': 's' },
    },
    ...overrides,
  });

describe('IntegrationConnectDialog credential flows', () => {
  beforeEach(resetConnectDialogMocks);

  describe('api key connection', () => {
    it('saves a single credential into the service env and keeps catalog tuning', async () => {
      const entry = makeEntry({
        mcpConfig: {
          name: 'svc',
          type: 'stdio',
          command: 'npx',
          args: ['-y', 'svc-mcp'],
          env: { BASE: '1' },
          description: 'Svc MCP',
          hostSerial: true,
          keepaliveInterval: 45,
        },
      });
      const { onConnected } = renderDialog(entry);

      fireEvent.change(screen.getByPlaceholderText('credentialPlaceholder'), { target: { value: ' secret ' } });
      clickConnect();

      await waitFor(() => expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1));
      const expectedConfig = {
        name: 'svc',
        type: 'stdio',
        url: '',
        command: 'npx',
        args: ['-y', 'svc-mcp'],
        description: 'Svc MCP',
        enabled: true,
        headers: null,
        extra_params: { env: { BASE: '1', SVC_TOKEN: 'secret' } },
      };
      expect(mockGateMcpEnable).toHaveBeenCalledExactlyOnceWith(expectedConfig, { acknowledgedHighRisks: false });
      expect(mockSetMCPConfigs).toHaveBeenCalledExactlyOnceWith([
        { ...expectedConfig, hostSerial: true, keepaliveInterval: 45, lastScanSummary: SCAN_SUMMARY },
      ]);
      expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'connectSuccess' });
      expect(onConnected).toHaveBeenCalledTimes(1);
      expect(mockApiRequest).not.toHaveBeenCalled();
    });

    it('injects multi-field credentials according to their inject mode', async () => {
      renderDialog(multiFieldEntry());

      fireEvent.change(screen.getByPlaceholderText('API Key'), { target: { value: ' key-1 ' } });
      fireEvent.change(screen.getByPlaceholderText('Auth Header'), { target: { value: 'header-1' } });
      fireEvent.change(screen.getByPlaceholderText('Project'), { target: { value: 'proj-1' } });
      clickConnect();

      await waitFor(() => expect(mockGateMcpEnable).toHaveBeenCalledTimes(1));
      expect(mockGateMcpEnable).toHaveBeenCalledExactlyOnceWith(
        {
          name: 'svc',
          type: 'stdio',
          url: '',
          command: 'run',
          args: ['--project', 'proj-1'],
          description: '',
          enabled: true,
          headers: { 'X-Static': 's', 'X-Auth': 'header-1' },
          extra_params: { env: { BASE: '1', API_KEY: 'key-1' } },
        },
        { acknowledgedHighRisks: false },
      );
    });

    it('asks for the first missing multi-field credential with its localized label', () => {
      renderDialog(multiFieldEntry(), 'zh');

      fireEvent.change(screen.getByPlaceholderText('密钥'), { target: { value: 'key-1' } });
      fireEvent.change(screen.getByPlaceholderText('认证头'), { target: { value: 'header-1' } });
      clickConnect();

      expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: '项目 credentialRequired', variant: 'destructive' });
      expect(mockGateMcpEnable).not.toHaveBeenCalled();
    });

    it('rejects an empty single credential before touching the gate', () => {
      renderDialog(makeEntry());

      clickConnect();

      expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'credentialRequired', variant: 'destructive' });
      expect(mockGateMcpEnable).not.toHaveBeenCalled();
      expect(mockSetMCPConfigs).not.toHaveBeenCalled();
    });

    it('refuses a service that is already configured and re-enables the button', async () => {
      storeState.mcpConfigs = [makeStoredConfig('svc')];
      renderDialog(makeEntry());

      fireEvent.change(screen.getByPlaceholderText('credentialPlaceholder'), { target: { value: 'secret' } });
      clickConnect();

      await waitFor(() =>
        expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'alreadyConnected', variant: 'destructive' }),
      );
      expect(mockGateMcpEnable).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
    });
  });

  describe('connectivity probe', () => {
    // Only loopback targets are probed; remote hosted entries skip the probe
    // and are verified by the security gate handshake instead.
    const loopbackEntry = () =>
      makeEntry({
        authType: 'none',
        envKey: null,
        mcpConfig: { name: 'svc', type: 'streamable_http', url: 'http://127.0.0.1:8000/mcp' },
      });

    it('connects after a probe that reports cloud_not_supported without a block flag', async () => {
      mockApiRequest.mockResolvedValueOnce({ status: 'cloud_not_supported' });
      renderDialog(loopbackEntry());

      clickConnect();

      await waitFor(() => expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1));
      expect(mockApiRequest).toHaveBeenCalledExactlyOnceWith('/integrations/mcp/probe', {
        method: 'POST',
        body: JSON.stringify({ url: 'http://127.0.0.1:8000/mcp', timeout: 5 }),
      });
      expect(screen.queryByText('probeCloudLoopbackBlocked')).not.toBeInTheDocument();
    });

    it('shows the unreachable message and keeps the config out when the probe request fails', async () => {
      mockApiRequest.mockRejectedValueOnce(new Error('network down'));
      renderDialog(loopbackEntry());

      clickConnect();

      expect(await screen.findByText('probeUnreachable')).toBeInTheDocument();
      expect(mockGateMcpEnable).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
    });
  });

  describe('security gate', () => {
    const noAuthEntry = () => makeEntry({ authType: 'none', envKey: null });
    const needsAcknowledgement = {
      needsAcknowledgement: true,
      allowed: false,
      scanResult: { findings: [{ threatType: 'shell' }] },
      verifyError: null,
      verifyFindings: [],
    };

    it('holds the config behind the acknowledgement dialog and saves it once confirmed', async () => {
      mockGateMcpEnable.mockResolvedValueOnce(needsAcknowledgement);
      renderDialog(noAuthEntry());

      clickConnect();

      expect(await screen.findByTestId('scan-ack')).toBeInTheDocument();
      expect(screen.getByTestId('scan-ack-server')).toHaveTextContent('svc');
      expect(screen.getByTestId('scan-ack-findings')).toHaveTextContent('1');
      expect(mockSetMCPConfigs).not.toHaveBeenCalled();

      // The Radix dialog marks its siblings aria-hidden, so the stub's buttons are queried by text.
      fireEvent.click(screen.getByText('ack-confirm'));

      await waitFor(() => expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1));
      expect(mockGateMcpEnable).toHaveBeenCalledTimes(2);
      expect(mockGateMcpEnable).toHaveBeenNthCalledWith(2, expect.objectContaining({ name: 'svc' }), {
        acknowledgedHighRisks: true,
      });
      expect(screen.queryByTestId('scan-ack')).not.toBeInTheDocument();
    });

    it('drops the pending config when the acknowledgement is cancelled', async () => {
      mockGateMcpEnable.mockResolvedValueOnce(needsAcknowledgement);
      renderDialog(noAuthEntry());

      clickConnect();
      await screen.findByTestId('scan-ack');
      fireEvent.click(screen.getByText('ack-cancel'));

      expect(screen.queryByTestId('scan-ack')).not.toBeInTheDocument();
      expect(mockGateMcpEnable).toHaveBeenCalledTimes(1);
      expect(mockSetMCPConfigs).not.toHaveBeenCalled();
    });

    it('reports the blocked reason when the gate refuses the config', async () => {
      mockGateMcpEnable.mockResolvedValueOnce({
        needsAcknowledgement: false,
        allowed: false,
        scanResult: { findings: [] },
        verifyError: 'unverified',
        verifyFindings: [],
      });
      renderDialog(noAuthEntry());

      clickConnect();

      await waitFor(() =>
        expect(mockToast).toHaveBeenCalledExactlyOnceWith({
          title: 'connectFailed',
          description: 'blocked',
          variant: 'destructive',
        }),
      );
      expect(mockSetMCPConfigs).not.toHaveBeenCalled();
      expect(screen.queryByTestId('scan-ack')).not.toBeInTheDocument();
    });

    it('keeps the connect button busy until the scan settles so a second click cannot start another run', async () => {
      let finishScan: (result: typeof GATE_ALLOWED) => void = () => undefined;
      mockGateMcpEnable.mockReturnValueOnce(
        new Promise<typeof GATE_ALLOWED>((resolve) => {
          finishScan = resolve;
        }),
      );
      renderDialog(noAuthEntry());

      clickConnect();

      const busyButton = await screen.findByRole('button', { name: 'connecting' });
      expect(busyButton).toBeDisabled();
      fireEvent.click(busyButton);
      expect(mockGateMcpEnable).toHaveBeenCalledTimes(1);

      finishScan(GATE_ALLOWED);

      await waitFor(() => expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1));
    });
  });

  describe('dialog content', () => {
    it.each<[CatalogLocale, string, string, string]>([
      ['en', 'Guide EN', 'Help EN', 'Service'],
      ['zh', '中文指引', '中文帮助', '服务'],
    ])('renders the %s guide, help text and credential link', (locale, guide, help, description) => {
      renderDialog(
        makeEntry({
          postConnectGuide: 'Guide EN',
          postConnectGuideZh: '中文指引',
          helpText: 'Help EN',
          helpTextZh: '中文帮助',
          helpUrl: 'https://svc.example/keys',
        }),
        locale,
      );

      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.getByText(description)).toBeInTheDocument();
      expect(screen.getByText(guide)).toBeInTheDocument();
      expect(screen.getByText(help)).toBeInTheDocument();
      const link = screen.getByRole('link', { name: 'getCredential' });
      expect(link).toHaveAttribute('href', 'https://svc.example/keys');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('closes through the cancel button', () => {
      const { onClose } = renderDialog(makeEntry());

      fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
