/** @vitest-environment jsdom */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { ArchiveOutcome, ArchiveStatus, ImportReport } from '@/services/instanceArchive';
import type { AutoBackup } from '@/services/instanceAutoBackup';
import { ImportCard } from '../ImportCard';
import InstanceArchivePanel from '../InstanceArchivePanel';
import { OutcomeNotifier } from '../OutcomeNotifier';
import { QueuedRestartNotice } from '../QueuedRestartNotice';

const { service, autoBackup } = vi.hoisted(() => ({
  autoBackup: { get: vi.fn(), update: vi.fn(), runNow: vi.fn() },
  service: {
    getStatus: vi.fn(),
    startExport: vi.fn(),
    getExport: vi.fn(),
    discardExport: vi.fn(),
    downloadExport: vi.fn(),
    uploadArchive: vi.fn(),
    stageImport: vi.fn(),
    confirmImport: vi.fn(),
    cancelImport: vi.fn(),
    getOutcome: vi.fn(),
    acknowledgeOutcome: vi.fn(),
    queueRollback: vi.fn(),
  },
}));

vi.mock('@/services/instanceArchive', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/instanceArchive')>()),
  instanceArchiveService: service,
}));
vi.mock('@/services/instanceAutoBackup', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/instanceAutoBackup')>()),
  instanceAutoBackupService: autoBackup,
}));

const stableT = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${Object.values(params).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const apiError = (code: string, status = 400) => new ApiError('server wording', status, [], undefined, code);

const report = (overrides: Partial<ImportReport> = {}): ImportReport => ({
  session_id: 's1',
  created_at: '2026-09-13T12:00:00Z',
  counts: { chats: 12, messages: 340 },
  current_counts: {},
  executable: {},
  reentry: [],
  paused_jobs: 0,
  missing_paths: 0,
  unreadable_count: 0,
  identity_dropped: false,
  config_key_carried: false,
  ...overrides,
});

const status = (overrides: Partial<ArchiveStatus> = {}): ArchiveStatus => ({
  supported: true,
  can_protect_secrets: true,
  restart_mode: 'process',
  pending_operation: null,
  rollback_available: false,
  ...overrides,
});

const outcome = (overrides: Partial<ArchiveOutcome> = {}): ArchiveOutcome => ({
  operation: 'import',
  status: 'restored',
  completed_at: '2026-10-13T00:00:00Z',
  summary: { chats: 5, messages: 0 },
  reentry: [],
  error_code: null,
  rollback_available: false,
  ...overrides,
});

const autoBackupState = (overrides: Partial<AutoBackup> = {}): AutoBackup => ({
  supported: true,
  enabled: false,
  frequency: 'daily',
  keep: 3,
  directory: '/Users/me/.myrm/backups/instance',
  default_directory: true,
  folder_available: true,
  running: false,
  overdue: false,
  last_success_at: null,
  last_success_size: null,
  consecutive_failures: 0,
  last_error_code: null,
  backups: [],
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  autoBackup.get.mockResolvedValue(autoBackupState({ supported: false }));
  service.acknowledgeOutcome.mockResolvedValue(undefined);
  service.cancelImport.mockResolvedValue(undefined);
  service.discardExport.mockResolvedValue(undefined);
});

describe('ImportCard', () => {
  const chooseFile = () => {
    const file = new File(['zip'], 'backup.zip', { type: 'application/zip' });
    fireEvent.change(screen.getByTestId('instance-archive-file'), { target: { files: [file] } });
  };

  it('walks upload, review and confirm, then tells the parent a swap is queued', async () => {
    service.uploadArchive.mockResolvedValue({ session_id: 's1' });
    service.stageImport.mockResolvedValue(report({ reentry: ['config:mcpServers'], paused_jobs: 2 }));
    service.confirmImport.mockResolvedValue({ operation: 'import', requires_restart: true });
    const onQueued = vi.fn();

    render(<ImportCard onQueued={onQueued} />);
    chooseFile();

    expect(await screen.findByText('verified')).toBeInTheDocument();
    expect(screen.getByText('counts.chats')).toBeInTheDocument();
    expect(screen.getByText('mcpConnections')).toBeInTheDocument();
    expect(screen.getByText('pausedJobs:2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'confirm' }));

    await waitFor(() => expect(service.confirmImport).toHaveBeenCalledWith('s1', false));
    expect(onQueued).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('queued')).toBeInTheDocument();
  });

  it('keeps confirm locked until executable content is explicitly trusted', async () => {
    service.uploadArchive.mockResolvedValue({ session_id: 's1' });
    service.stageImport.mockResolvedValue(report({ executable: { scheduled_commands: 2 } }));
    service.confirmImport.mockResolvedValue({ operation: 'import', requires_restart: true });

    render(<ImportCard onQueued={vi.fn()} />);
    chooseFile();

    const confirm = await screen.findByRole('button', { name: 'confirm' });
    expect(confirm).toBeDisabled();
    expect(screen.getByText('executable.scheduled_commands:2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'trust' }));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(service.confirmImport).toHaveBeenCalledWith('s1', true));
  });

  it('asks for the passphrase when the backup carries protected keys', async () => {
    service.uploadArchive.mockResolvedValue({ session_id: 's1' });
    service.stageImport.mockRejectedValueOnce(apiError('passphrase_required')).mockResolvedValueOnce(report());

    render(<ImportCard onQueued={vi.fn()} />);
    chooseFile();

    expect(await screen.findByText('passphraseTitle')).toBeInTheDocument();
    const unlock = screen.getByRole('button', { name: 'unlock' });
    expect(unlock).toBeDisabled();

    fireEvent.change(screen.getByLabelText('passphrase'), { target: { value: 'open sesame' } });
    fireEvent.click(unlock);

    await waitFor(() => expect(service.stageImport).toHaveBeenLastCalledWith('s1', { passphrase: 'open sesame' }));
    expect(await screen.findByText('verified')).toBeInTheDocument();
  });

  it('can restore without the keys', async () => {
    service.uploadArchive.mockResolvedValue({ session_id: 's1' });
    service.stageImport.mockRejectedValueOnce(apiError('passphrase_required')).mockResolvedValueOnce(report());

    render(<ImportCard onQueued={vi.fn()} />);
    chooseFile();
    fireEvent.click(await screen.findByRole('button', { name: 'skipKeys' }));

    await waitFor(() => expect(service.stageImport).toHaveBeenLastCalledWith('s1', { skipSecrets: true }));
  });

  it('drops a rejected backup and shows localized copy', async () => {
    service.uploadArchive.mockResolvedValue({ session_id: 's1' });
    service.stageImport.mockRejectedValue(apiError('newer_schema'));

    render(<ImportCard onQueued={vi.fn()} />);
    chooseFile();

    expect(await screen.findByText('newer_schema')).toBeInTheDocument();
    expect(service.cancelImport).toHaveBeenCalledWith('s1');
    expect(screen.getByRole('button', { name: 'choose' })).toBeInTheDocument();
    expect(screen.queryByText('server wording')).not.toBeInTheDocument();
  });
});

describe('OutcomeNotifier', () => {
  it('reports a restore once, links to the credentials to enter again and acknowledges on close', async () => {
    service.getOutcome.mockResolvedValue(outcome({ reentry: ['config:providers', 'table:vault_credentials'] }));

    render(<OutcomeNotifier />);

    expect(await screen.findByText('restoredImport')).toBeInTheDocument();
    expect(screen.getByText('chats')).toBeInTheDocument();
    expect(screen.queryByText('messages')).not.toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: 'open' });
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/settings/models', '/settings/credentials']);

    fireEvent.click(screen.getByRole('button', { name: 'done' }));
    await waitFor(() => expect(service.acknowledgeOutcome).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('restoredImport')).not.toBeInTheDocument();
  });

  it('shows a failed swap with localized copy', async () => {
    service.getOutcome.mockResolvedValue(outcome({ status: 'failed', error_code: 'promotion_failed' }));

    render(<OutcomeNotifier />);

    expect(await screen.findByText('failedTitle')).toBeInTheDocument();
    expect(screen.getByText('restore_failed')).toBeInTheDocument();
  });

  it('stays silent when there is nothing to report or the swap is still waiting', async () => {
    service.getOutcome.mockResolvedValueOnce(null);
    const { unmount } = render(<OutcomeNotifier />);
    await waitFor(() => expect(service.getOutcome).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    unmount();

    service.getOutcome.mockResolvedValueOnce(outcome({ status: 'waiting' }));
    render(<OutcomeNotifier />);
    await waitFor(() => expect(service.getOutcome).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('queues an undo and asks for a restart', async () => {
    service.getOutcome.mockResolvedValue(outcome({ rollback_available: true }));
    service.queueRollback.mockResolvedValue({ operation: 'rollback', requires_restart: true });
    service.getStatus.mockResolvedValue(status({ pending_operation: 'rollback', restart_mode: 'sandbox' }));

    render(<OutcomeNotifier />);
    fireEvent.click(await screen.findByRole('button', { name: 'undo' }));

    await waitFor(() => expect(service.queueRollback).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('button', { name: 'now' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'undo' })).not.toBeInTheDocument();
  });
});

describe('InstanceArchivePanel', () => {
  it('renders nothing when the endpoints are not reachable', async () => {
    service.getStatus.mockRejectedValue(apiError('forbidden', 403));

    const { container } = render(<InstanceArchivePanel />);
    await waitFor(() => expect(service.getStatus).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it('is honest when the layout cannot be backed up', async () => {
    service.getStatus.mockResolvedValue(status({ supported: false }));

    render(<InstanceArchivePanel />);

    expect(await screen.findByText('unsupported')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'start' })).not.toBeInTheDocument();
  });

  it('offers export and import, and an undo only when nothing is pending', async () => {
    service.getStatus.mockResolvedValue(status({ rollback_available: true }));

    render(<InstanceArchivePanel />);

    expect(await screen.findByRole('button', { name: 'start' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'choose' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'action' })).toBeInTheDocument();
  });

  it('adds scheduled backup below export and import where the server offers it', async () => {
    service.getStatus.mockResolvedValue(status());
    autoBackup.get.mockResolvedValue(autoBackupState());

    render(<InstanceArchivePanel />);

    expect(await screen.findByRole('switch', { name: 'enable' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'start' })).toBeInTheDocument();
  });

  it('leaves scheduled backup out where the server does not offer it', async () => {
    service.getStatus.mockResolvedValue(status());

    render(<InstanceArchivePanel />);
    await screen.findByRole('button', { name: 'start' });
    await waitFor(() => expect(autoBackup.get).toHaveBeenCalled());

    expect(screen.queryByRole('switch', { name: 'enable' })).not.toBeInTheDocument();
  });

  it('never asks for scheduled backup when the layout cannot be backed up at all', async () => {
    service.getStatus.mockResolvedValue(status({ supported: false }));

    render(<InstanceArchivePanel />);
    await screen.findByText('unsupported');

    expect(autoBackup.get).not.toHaveBeenCalled();
  });

  it('replaces the undo with a restart prompt while a swap is queued', async () => {
    service.getStatus.mockResolvedValue(
      status({ rollback_available: true, pending_operation: 'import', restart_mode: 'sandbox' }),
    );

    render(<InstanceArchivePanel />);

    expect(await screen.findByRole('button', { name: 'now' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'action' })).not.toBeInTheDocument();
  });
});

describe('QueuedRestartNotice', () => {
  it('lets sandbox deployments restart on request', async () => {
    service.getStatus.mockResolvedValue(status({ restart_mode: 'sandbox' }));

    render(<QueuedRestartNotice />);

    expect(await screen.findByRole('button', { name: 'now' })).toBeInTheDocument();
  });

  it('asks bare local processes to be restarted by the user', async () => {
    service.getStatus.mockResolvedValue(status({ restart_mode: 'process' }));

    render(<QueuedRestartNotice />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(await screen.findByText('manual')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'now' })).not.toBeInTheDocument();
  });
});
