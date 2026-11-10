/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';
import { duplicateCronJob, updateCronJob } from '@/services/cron';
import type { CronJob } from '@/services/cron.types';

import CronJobCard from '../CronJobCard';

const mocks = vi.hoisted(() => {
  const cronState = {
    pauseJob: vi.fn(),
    resumeJob: vi.fn(),
    triggerJob: vi.fn(),
    fetchJobs: vi.fn(),
    jobs: [] as unknown[],
  };
  const providerState = {
    providers: [] as unknown[],
    defaultModelConfig: { baseModel: { primary: { providerId: 'openai', model: 'gpt-4o' } } },
  };
  return {
    cronState,
    providerState,
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    deployMode: { isSandbox: false, isLocal: true, isLoading: false },
    // 翻译函数必须是稳定引用：每次渲染都新建会让依赖它的 hook 反复重建。
    translate: (key: string, params?: Record<string, string | number>) =>
      params ? `${key}|${Object.values(params).join(',')}` : key,
  };
});

vi.mock('next-intl', () => ({
  useTranslations: () => mocks.translate,
  useLocale: () => 'en',
}));
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));
vi.mock('@/hooks/shared/useDeployMode', () => ({ useDeployMode: () => mocks.deployMode }));
vi.mock('@/services/cron', () => ({ updateCronJob: vi.fn(), duplicateCronJob: vi.fn() }));
vi.mock('@/store/useCronStore', () => ({
  default: (selector: (state: typeof mocks.cronState) => unknown) => selector(mocks.cronState),
}));
vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (state: typeof mocks.providerState) => unknown) => selector(mocks.providerState),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { chatHistoryItems: unknown[] }) => unknown) => selector({ chatHistoryItems: [] }),
}));
vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: { agents: unknown[] }) => unknown) => selector({ agents: [] }),
}));
vi.mock('@/store/config/providerTypes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/store/config/providerTypes')>()),
  getRoutedModelName: (providerId: string, model: string) => `${providerId}/${model}`,
}));
vi.mock('@/components/features/app-shell/model-picker-popover', () => ({
  default: ({ trigger, onSelect }: { trigger: ReactNode; onSelect: (providerId: string, model: string) => void }) => (
    <div>
      {trigger}
      <button onClick={() => onSelect('openai', 'gpt-x')}>pick-model</button>
    </div>
  ),
}));
vi.mock('@/components/features/settings/sections/integration/channels/ChannelIcon', () => ({ default: () => null }));
vi.mock('../CronWorkflowTemplateBinding', () => ({ CronWorkflowTemplateBadge: () => null }));

const BASE_JOB: CronJob = {
  id: 'job-1',
  name: 'Daily digest',
  job_type: 'agent',
  status: 'active',
  schedule: { kind: 'interval', interval_ms: 3_600_000 },
  prompt: 'Summarize the news',
  context_from: [],
  max_retries: 0,
  retry_backoff_ms: 0,
  timeout_seconds: 0,
  misfire_grace_seconds: 60,
  cooldown_seconds: 0,
  fire_count: 0,
  session_target: 'isolated',
  required_capabilities: [],
  tools_allowed: [],
  allowed_roots: [],
  delete_after_run: false,
  run_retention_days: 30,
  deduplicate: false,
  skip_if_active: false,
  consecutive_failures: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderCard(job: CronJob, handlers: { onSelect?: () => void; onRequestDelete?: (job: CronJob) => void } = {}) {
  const onSelect = handlers.onSelect ?? vi.fn();
  const onRequestDelete = handlers.onRequestDelete ?? vi.fn();
  const view = render(
    <TooltipProvider>
      <CronJobCard job={job} onSelect={onSelect} onRequestDelete={onRequestDelete} />
    </TooltipProvider>,
  );
  const actionButton = (icon: string): HTMLButtonElement => {
    const button = view.container.querySelector(`svg[class*="lucide-${icon}"]`)?.closest('button');
    if (!button) {
      throw new Error(`no action button with the ${icon} icon`);
    }
    return button;
  };
  return { ...view, onSelect, onRequestDelete, actionButton };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.deployMode.isSandbox = false;
  mocks.deployMode.isLocal = true;
  mocks.cronState.pauseJob.mockResolvedValue(undefined);
  mocks.cronState.resumeJob.mockResolvedValue(undefined);
  mocks.cronState.triggerJob.mockResolvedValue(undefined);
  vi.mocked(updateCronJob).mockResolvedValue(BASE_JOB);
  vi.mocked(duplicateCronJob).mockResolvedValue(BASE_JOB);
});

describe('CronJobCard', () => {
  it('shows the name, status and prompt, and opens the job when the card is clicked', () => {
    const { onSelect } = renderCard(BASE_JOB);

    expect(screen.getByText('Daily digest')).toBeInTheDocument();
    expect(screen.getByText('statusActive')).toBeInTheDocument();
    expect(screen.getByText('Summarize the news')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Daily digest'));
    expect(onSelect).toHaveBeenCalledWith(BASE_JOB);
  });

  it('pauses an active job and confirms with a toast', async () => {
    const { actionButton, onSelect } = renderCard(BASE_JOB);

    fireEvent.click(actionButton('pause'));

    await waitFor(() => expect(mocks.cronState.pauseJob).toHaveBeenCalledWith('job-1'));
    expect(mocks.toastSuccess).toHaveBeenCalledWith('pauseSuccess|Daily digest');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('resumes a paused job that has not expired', async () => {
    const { actionButton } = renderCard({ ...BASE_JOB, status: 'paused' });

    fireEvent.click(actionButton('play'));

    await waitFor(() => expect(mocks.cronState.resumeJob).toHaveBeenCalledWith('job-1'));
    expect(mocks.toastSuccess).toHaveBeenCalledWith('resumeSuccess|Daily digest');
  });

  it('blocks resuming a paused job that used up its fires', () => {
    const { actionButton } = renderCard({ ...BASE_JOB, status: 'paused', max_fires: 3, fire_count: 3 });

    expect(actionButton('play')).toBeDisabled();
  });

  it('reports a failed pause', async () => {
    mocks.cronState.pauseJob.mockRejectedValue(new Error('boom'));
    const { actionButton } = renderCard(BASE_JOB);

    fireEvent.click(actionButton('pause'));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('actionFail'));
  });

  it('triggers a run and disables the trigger button while it settles', async () => {
    const { actionButton } = renderCard(BASE_JOB);

    fireEvent.click(actionButton('rotate-cw'));

    await waitFor(() => expect(mocks.cronState.triggerJob).toHaveBeenCalledWith('job-1'));
    expect(mocks.toastSuccess).toHaveBeenCalledWith('triggerSuccess|Daily digest');
    await waitFor(() => expect(actionButton('rotate-cw')).toBeDisabled());
  });

  it('duplicates the job and refreshes the list', async () => {
    const { actionButton } = renderCard(BASE_JOB);

    fireEvent.click(actionButton('copy'));

    await waitFor(() => expect(duplicateCronJob).toHaveBeenCalledWith('job-1'));
    expect(mocks.toastSuccess).toHaveBeenCalledWith('duplicateSuccess|Daily digest');
    expect(mocks.cronState.fetchJobs).toHaveBeenCalledWith(true);
  });

  it('asks to delete the job with the destructive text token on the button', () => {
    const { actionButton, onRequestDelete, onSelect } = renderCard(BASE_JOB);

    const deleteButton = actionButton('trash-2');
    expect(deleteButton).toHaveClass('text-destructive-text');
    fireEvent.click(deleteButton);

    expect(onRequestDelete).toHaveBeenCalledWith(BASE_JOB);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('saves the model picked in the popover and refreshes the list', async () => {
    renderCard(BASE_JOB);

    fireEvent.click(screen.getByText('pick-model'));

    await waitFor(() => expect(updateCronJob).toHaveBeenCalledWith('job-1', { model: 'openai/gpt-x' }));
    expect(mocks.cronState.fetchJobs).toHaveBeenCalledWith(true);
  });

  it('shows the overdue banner for the deploy mode only when the next run is long past', () => {
    const overdue = { ...BASE_JOB, next_run_at: new Date(Date.now() - 3_600_000).toISOString() };

    const { unmount } = renderCard(overdue);
    expect(screen.getByText(/^overdueBannerLocal\|/)).toBeInTheDocument();
    unmount();

    mocks.deployMode.isSandbox = true;
    mocks.deployMode.isLocal = false;
    const cloud = renderCard(overdue);
    expect(screen.getByText(/^overdueBannerCloud\|/)).toBeInTheDocument();
    cloud.unmount();

    renderCard({ ...BASE_JOB, next_run_at: new Date(Date.now() + 3_600_000).toISOString() });
    expect(screen.queryByText(/^overdueBanner/)).not.toBeInTheDocument();
  });

  it('shows the failure, fire count and context badges', () => {
    renderCard({
      ...BASE_JOB,
      consecutive_failures: 3,
      max_fires: 5,
      fire_count: 2,
      context_from: ['job-2'],
      skill_ids: ['web-search'],
    });

    expect(screen.getByText('consecutiveFailures|3')).toBeInTheDocument();
    expect(screen.getByText('fireCountValue|2,5')).toBeInTheDocument();
    expect(screen.getByText('contextFromBadge|1')).toBeInTheDocument();
    expect(screen.getByText('web-search')).toBeInTheDocument();
  });
});
