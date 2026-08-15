/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConnectWizardDialog } from '../ConnectWizardDialog';

const listConnectProfilesMock = vi.hoisted(() => vi.fn());
const generateConnectConfigMock = vi.hoisted(() => vi.fn());
const generateAgentPluginBundleMock = vi.hoisted(() => vi.fn());
const revokeConnectMock = vi.hoisted(() => vi.fn());
const runConnectDoctorMock = vi.hoisted(() => vi.fn());
const listAgentsMock = vi.hoisted(() => vi.fn());
const countProviderTreesMock = vi.hoisted(() => vi.fn());
const triggerDownloadMock = vi.hoisted(() => vi.fn());
const buildZipFromFilesMock = vi.hoisted(() => vi.fn());
const toastErrorMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  'title': 'Connect memory',
  'description': 'description',
  'selectMyrmAgent': 'Select agent',
  'selectMyrmAgentDesc': 'selectMyrmAgentDesc',
  'selectExternalTool': 'Select external tool',
  'selectAgentDesc': 'selectAgentDesc',
  'configFile': 'Config file',
  'generate': 'Generate',
  'generating': 'Generating...',
  'agentPlugin': 'Agent Plugin',
  'agentPluginDesc': 'agentPluginDesc',
  'agentPluginEmbedToken': 'agentPluginEmbedToken',
  'agentPluginEmbedTokenHint': 'agentPluginEmbedTokenHint',
  'agentPluginGenerate': 'Generate Plugin',
  'configReady': 'configReady',
  'memoryScopeAgent': 'Scope: {agent}',
  'token': 'Token',
  'tokenWarning': 'tokenWarning',
  'copy': 'Copy',
  'copied': 'Copied',
  'copyConfig': 'copyConfig',
  'doctor': 'Doctor',
  'doctorRunning': 'doctorRunning',
  'revoke': 'Revoke',
  'revokeConfirm': 'Confirm revoke',
  'close': 'Close',
  'clearSyncedMemory': 'clearSyncedMemory',
  'agentPluginReady': 'agentPluginReady',
  'pluginFile': 'pluginFile',
  'download': 'Download',
  'downloadBundle': 'Download all',
  'downloadingBundle': 'Downloading...',
  'downloadBundleFailed': 'Download failed',
  'status.ready': 'Ready',
};

const stableT = (key: string, values?: Record<string, string | number>): string => {
  let text = TRANSLATIONS[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/connect', () => ({
  AGENT_PLUGIN_PROFILE_ID: 'myrm-agent-plugin',
  listConnectProfiles: listConnectProfilesMock,
  generateConnectConfig: generateConnectConfigMock,
  generateAgentPluginBundle: generateAgentPluginBundleMock,
  revokeConnect: revokeConnectMock,
  runConnectDoctor: runConnectDoctorMock,
}));

vi.mock('@/services/agent', () => ({
  listAgents: listAgentsMock,
}));

vi.mock('@/services/memory/integration', () => ({
  countProviderTrees: countProviderTreesMock,
}));

vi.mock('@/lib/utils/fileUtils', () => ({
  getFileExtension: (name: string) => name.split('.').pop() ?? '',
  getMimeType: () => 'application/octet-stream',
  sanitizeFilename: (name: string) => name,
  buildZipFromFiles: buildZipFromFilesMock,
  triggerDownload: triggerDownloadMock,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: toastErrorMock },
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name?: string | null) => name ?? _id,
}));

const PROFILE = {
  id: 'cursor',
  label: 'Cursor',
  status: 'ready',
  description: 'Cursor editor',
  config_file_path: '~/.cursor/mcp.json',
};

const AGENTS = [
  { id: 'default', name: 'Default Agent' },
  { id: 'researcher', name: 'Researcher' },
];

const PLUGIN_RESULT = {
  agent_id: 'default',
  token: 'tok_123',
  instructions: 'Install the bundle',
  files: {
    'plugin.json': '{"name":"myrm-memory"}',
    'mcp.json': '{"mcpServers":{}}',
    'skills/myrm-memory/SKILL.md': '# Memory skill',
  },
};

async function navigateToPluginStep() {
  render(<ConnectWizardDialog open onOpenChange={() => {}} />);
  await screen.findByText('Cursor');
  fireEvent.click(screen.getByText('Cursor'));
  fireEvent.click(screen.getByRole('button', { name: 'Generate Plugin' }));
  await screen.findByText('agentPluginReady');
}

describe('ConnectWizardDialog bundle download', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listConnectProfilesMock.mockResolvedValue([PROFILE]);
    listAgentsMock.mockResolvedValue({ items: AGENTS });
    generateConnectConfigMock.mockResolvedValue({
      agent_id: 'default',
      token: 'cfg_tok',
      instructions: 'Add to cursor',
      config_json: { _toml_snippet: 'snippet' },
    });
    generateAgentPluginBundleMock.mockResolvedValue(PLUGIN_RESULT);
    buildZipFromFilesMock.mockResolvedValue(new Blob(['zip'], { type: 'application/zip' }));
    triggerDownloadMock.mockResolvedValue(undefined);
    revokeConnectMock.mockResolvedValue(undefined);
    runConnectDoctorMock.mockResolvedValue({ healthy: true, detail: 'ok' });
    countProviderTreesMock.mockResolvedValue(0);
  });

  it('renders the bundle zip download button on the plugin step', async () => {
    await navigateToPluginStep();
    expect(screen.getByRole('button', { name: 'Download all' })).toBeInTheDocument();
  });

  it('downloads the whole bundle as a zip named after the agent', async () => {
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download all' }));

    await waitFor(() => {
      expect(buildZipFromFilesMock).toHaveBeenCalledWith(PLUGIN_RESULT.files);
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'myrm-memory-Default Agent.zip');
    });
  });

  it('falls back to the generic zip name when the agent is unknown', async () => {
    generateAgentPluginBundleMock.mockResolvedValue({ ...PLUGIN_RESULT, agent_id: 'ghost' });
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download all' }));

    await waitFor(() => {
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'myrm-memory.zip');
    });
  });

  it('shows a toast when the zip build or download fails', async () => {
    buildZipFromFilesMock.mockRejectedValue(new Error('boom'));
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download all' }));

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Download failed');
    });
  });

  it('disables the zip button while a download is in flight', async () => {
    let release!: (value: Blob) => void;
    buildZipFromFilesMock.mockImplementation(
      () => new Promise<Blob>((resolve) => { release = resolve; }),
    );
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download all' }));

    expect(screen.getByRole('button', { name: 'Downloading...' })).toBeDisabled();
    release(new Blob(['zip']));
  });

  it('downloads the selected file individually', async () => {
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download' }));

    await waitFor(() => {
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), 'plugin.json');
    });
  });

  it('truncates an overly long agent name to 64 chars in the zip filename', async () => {
    const longName = 'A'.repeat(255);
    listAgentsMock.mockResolvedValue({ items: [{ id: 'default', name: longName }] });
    await navigateToPluginStep();

    fireEvent.click(screen.getByRole('button', { name: 'Download all' }));

    await waitFor(() => {
      expect(triggerDownloadMock).toHaveBeenCalledWith(
        expect.any(Blob),
        `myrm-memory-${'A'.repeat(64)}.zip`,
      );
    });
  });

  it('passes the embed token switch through to the bundle API', async () => {
    render(<ConnectWizardDialog open onOpenChange={() => {}} />);
    await screen.findByText('Cursor');
    fireEvent.click(screen.getByText('Cursor'));

    const embedSwitch = screen.getByRole('switch', { name: /agentPluginEmbedToken/ });
    fireEvent.click(embedSwitch);

    fireEvent.click(screen.getByRole('button', { name: 'Generate Plugin' }));
    await screen.findByText('agentPluginReady');

    expect(generateAgentPluginBundleMock).toHaveBeenCalledWith('default', true);
  });
});
