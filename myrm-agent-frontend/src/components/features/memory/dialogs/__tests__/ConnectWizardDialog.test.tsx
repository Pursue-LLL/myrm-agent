/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConnectWizardDialog } from '../ConnectWizardDialog';

const listConnectProfilesMock = vi.hoisted(() => vi.fn());
const generateConnectConfigMock = vi.hoisted(() => vi.fn());
const generateAgentPluginBundleMock = vi.hoisted(() => vi.fn());
const getAgentConnectCapabilitiesMock = vi.hoisted(() => vi.fn());
const revokeConnectMock = vi.hoisted(() => vi.fn());
const runConnectDoctorMock = vi.hoisted(() => vi.fn());
const listAgentsMock = vi.hoisted(() => vi.fn());
const countProviderTreesMock = vi.hoisted(() => vi.fn());
const triggerDownloadMock = vi.hoisted(() => vi.fn());
const buildZipFromFilesMock = vi.hoisted(() => vi.fn());
const toastErrorMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  title: 'Connect memory',
  description: 'description',
  selectMyrmAgent: 'Select agent',
  selectMyrmAgentDesc: 'selectMyrmAgentDesc',
  selectExternalTool: 'Select external tool',
  selectAgentDesc: 'selectAgentDesc',
  configFile: 'Config file',
  generate: 'Generate',
  generating: 'Generating...',
  agentPlugin: 'Agent Plugin',
  agentPluginDesc: 'agentPluginDesc',
  agentPluginEmbedToken: 'agentPluginEmbedToken',
  agentPluginEmbedTokenHint: 'agentPluginEmbedTokenHint',
  agentPluginGenerate: 'Generate Plugin',
  configReady: 'configReady',
  memoryScopeAgent: 'Scope: {agent}',
  token: 'Token',
  tokenWarning: 'tokenWarning',
  copy: 'Copy',
  copied: 'Copied',
  copyConfig: 'copyConfig',
  doctor: 'Doctor',
  doctorRunning: 'doctorRunning',
  revoke: 'Revoke',
  revokeConfirm: 'Confirm revoke',
  close: 'Close',
  clearSyncedMemory: 'clearSyncedMemory',
  agentPluginReady: 'agentPluginReady',
  pluginFile: 'pluginFile',
  download: 'Download',
  downloadBundle: 'Download all',
  downloadingBundle: 'Downloading...',
  downloadBundleFailed: 'Download failed',
  'status.ready': 'Ready',
  doctorHealthyVerified: 'doctorHealthyVerified',
  doctorHealthyTokenValid: 'doctorHealthyTokenValid',
  doctorDetailTokenEnv: 'doctorDetailTokenEnv',
  doctorDetailTokenMismatch: 'doctorDetailTokenMismatch',
  doctorUnhealthy: 'doctorUnhealthy',
  exposeDesktopTools: 'Expose Desktop Control Tools',
  exposeDesktopToolsDesc: 'Expose Semantic Desktop Control tools',
  exposeDesktopDisabledHint: 'Desktop automation not supported',
  exposeDesktopEnabledBadge: 'Desktop Automation Enabled',
  desktopToolsIncluded: 'Desktop tools: {tools}',
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
  getAgentConnectCapabilities: getAgentConnectCapabilitiesMock,
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
    getAgentConnectCapabilitiesMock.mockResolvedValue({
      agent_id: 'default',
      has_computer_use: false,
      desktop_deploy_supported: false,
      can_expose_desktop: false,
    });
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
      () =>
        new Promise<Blob>((resolve) => {
          release = resolve;
        }),
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
      expect(triggerDownloadMock).toHaveBeenCalledWith(expect.any(Blob), `myrm-memory-${'A'.repeat(64)}.zip`);
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

async function navigateToConfigStep() {
  const view = render(<ConnectWizardDialog open onOpenChange={() => {}} />);
  await screen.findByText('Cursor');
  fireEvent.click(screen.getByText('Cursor'));
  fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
  await screen.findByText('configReady');
  return view;
}

describe('ConnectWizardDialog doctor check', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listConnectProfilesMock.mockResolvedValue([PROFILE]);
    listAgentsMock.mockResolvedValue({ items: AGENTS });
    getAgentConnectCapabilitiesMock.mockResolvedValue({
      agent_id: 'default',
      has_computer_use: false,
      desktop_deploy_supported: false,
      can_expose_desktop: false,
    });
    generateConnectConfigMock.mockResolvedValue({
      agent_id: 'default',
      token: 'cfg_tok',
      instructions: 'Add to cursor',
      config_json: { _toml_snippet: 'snippet' },
    });
    countProviderTreesMock.mockResolvedValue(0);
    revokeConnectMock.mockResolvedValue({ profile_id: 'cursor', revoked: true, trees_removed: 0 });
  });

  it('renders the green doctor box when the check verifies', async () => {
    runConnectDoctorMock.mockResolvedValue({ healthy: true, detail: 'verified', severity: 'ok' });
    await navigateToConfigStep();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));

    const box = await screen.findByText('doctorHealthyVerified');
    expect(box.className).toContain('border-green-500/20');
  });

  it('renders the amber doctor box for a warn-level blind spot', async () => {
    runConnectDoctorMock.mockResolvedValue({ healthy: false, detail: 'token_env', severity: 'warn' });
    await navigateToConfigStep();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));

    const box = await screen.findByText('doctorDetailTokenEnv');
    expect(box.className).toContain('border-amber-500/20');
  });

  it('renders the red doctor box for a failed check', async () => {
    runConnectDoctorMock.mockResolvedValue({ healthy: false, detail: 'token_mismatch', severity: 'error' });
    await navigateToConfigStep();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));

    const box = await screen.findByText('doctorDetailTokenMismatch');
    expect(box.className).toContain('border-red-500/20');
  });

  it('prefers the server-owned severity over the healthy flag', async () => {
    runConnectDoctorMock.mockResolvedValue({ healthy: true, detail: 'token_valid', severity: 'warn' });
    await navigateToConfigStep();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));

    const box = await screen.findByText('doctorHealthyTokenValid');
    expect(box.className).toContain('border-amber-500/20');
  });

  it('falls back to the unhealthy box when the doctor API fails', async () => {
    runConnectDoctorMock.mockRejectedValue(new Error('boom'));
    await navigateToConfigStep();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));

    const box = await screen.findByText('doctorUnhealthy');
    expect(box.className).toContain('border-red-500/20');
  });
});

describe('ConnectWizardDialog desktop tools exposure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listConnectProfilesMock.mockResolvedValue([PROFILE]);
    listAgentsMock.mockResolvedValue({ items: AGENTS });
    getAgentConnectCapabilitiesMock.mockResolvedValue({
      agent_id: 'default',
      has_computer_use: true,
      desktop_deploy_supported: true,
      can_expose_desktop: true,
    });
    generateConnectConfigMock.mockResolvedValue({
      agent_id: 'default',
      token: 'cfg_tok',
      instructions: 'Add to cursor',
      config_json: { mcpServers: {} },
      expose_desktop: true,
      desktop_tools: ['desktop_snapshot_tool', 'desktop_interact_tool', 'desktop_vision_tool'],
    });
  });

  it('renders desktop toggle enabled when agent supports desktop control', async () => {
    render(<ConnectWizardDialog open onOpenChange={() => {}} />);
    await screen.findByText('Cursor');
    const toggle = await screen.findByRole('switch', { name: /Expose Desktop Control Tools/i });
    expect(toggle).not.toBeDisabled();
  });

  it('renders desktop toggle disabled when agent does not support desktop control', async () => {
    getAgentConnectCapabilitiesMock.mockResolvedValue({
      agent_id: 'default',
      has_computer_use: false,
      desktop_deploy_supported: false,
      can_expose_desktop: false,
    });
    render(<ConnectWizardDialog open onOpenChange={() => {}} />);
    await screen.findByText('Cursor');
    const toggle = await screen.findByRole('switch', { name: /Expose Desktop Control Tools/i });
    expect(toggle).toBeDisabled();
    expect(screen.getByText('Desktop automation not supported')).toBeInTheDocument();
  });

  it('passes expose_desktop true to generateConnectConfig when toggled', async () => {
    render(<ConnectWizardDialog open onOpenChange={() => {}} />);
    await screen.findByText('Cursor');
    fireEvent.click(screen.getByText('Cursor'));

    const toggle = await screen.findByRole('switch', { name: /Expose Desktop Control Tools/i });
    fireEvent.click(toggle);

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }));

    await waitFor(() => {
      expect(generateConnectConfigMock).toHaveBeenCalledWith('cursor', 'default', true);
    });
  });

  it('displays desktop enabled badge and tool names in config step', async () => {
    render(<ConnectWizardDialog open onOpenChange={() => {}} />);
    await screen.findByText('Cursor');
    fireEvent.click(screen.getByText('Cursor'));

    const toggle = await screen.findByRole('switch', { name: /Expose Desktop Control Tools/i });
    fireEvent.click(toggle);

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }));

    await screen.findByText('configReady');
    expect(screen.getByText('Desktop Automation Enabled')).toBeInTheDocument();
    expect(screen.getByText(/desktop_snapshot_tool/)).toBeInTheDocument();
  });
});
