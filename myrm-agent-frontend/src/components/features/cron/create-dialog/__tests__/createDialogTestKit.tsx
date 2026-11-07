import { fireEvent, render, screen, waitFor, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, vi, type Mock } from 'vitest';

import type { CronJob, CreateCronJobRequest, PrerequisiteCheckResponse } from '@/services/cron.types';
import type { WorkflowTemplateSummary } from '@/services/workflowTemplates';
import { settle } from '@/test-utils/fakeClock';
import CronJobCreateDialog from '../../CronJobCreateDialog';

/**
 * 创建弹窗测试共用工具：模块 mock（须在被测弹窗之前 import 本文件才会生效）、可变夹具状态、渲染与交互 helper。
 * 网络 / store / 审计面板等边界全部在此 mock，测试只断言弹窗的可见行为与提交给 `createJob` 的请求体。
 */

interface KitState {
  agents: Array<{ id: string; name: string }>;
  providerPrimary: { providerId: string; model: string } | null;
  chats: Array<{ id: string; title: string }>;
  canDismissAudit: boolean;
}

const hoisted = vi.hoisted(() => ({
  state: {
    agents: [],
    providerPrimary: null,
    chats: [],
    canDismissAudit: true,
  } as KitState,
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  apiRequest: vi.fn(),
  fetchAgents: vi.fn(),
  createJob: vi.fn(),
  prepareAudit: vi.fn(),
  listChannelStatuses: vi.fn(),
  fetchWorkflowTemplates: vi.fn(),
  checkCronPrerequisite: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: hoisted.toast }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: hoisted.apiRequest,
}));
vi.mock('@/store/useAgentStore', () => ({
  default: () => ({ agents: hoisted.state.agents, fetchAgents: hoisted.fetchAgents }),
}));
vi.mock('@/store/useProviderStore', () => ({
  default: () => ({ defaultModelConfig: { baseModel: { primary: hoisted.state.providerPrimary } } }),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (select: (store: { chatHistoryItems: KitState['chats'] }) => unknown) =>
    select({ chatHistoryItems: hoisted.state.chats }),
}));
vi.mock('@/store/useCronStore', () => ({ default: () => ({ createJob: hoisted.createJob }) }));
vi.mock('@/services/riskHeldToast', () => ({
  isRiskHeldError: (error: unknown) => (error as { riskHeld?: boolean } | null)?.riskHeld === true,
}));
vi.mock('@/services/channels', () => ({ listChannelStatuses: hoisted.listChannelStatuses }));
vi.mock('@/services/workflowTemplates', () => ({ fetchWorkflowTemplates: hoisted.fetchWorkflowTemplates }));
vi.mock('@/services/cron', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/cron')>()),
  checkCronPrerequisite: hoisted.checkCronPrerequisite,
}));
vi.mock('@/lib/cron/cronCreateAuditGate', () => ({
  prepareJobForSettingsAudit: hoisted.prepareAudit,
  canDismissSettingsAuditFlow: () => hoisted.state.canDismissAudit,
}));
vi.mock('@/components/features/cron/CronJobAuditPanel', () => ({
  CronJobAuditPanel: ({ jobId, initialJob, onJobChange }: AuditPanelProps) => (
    <div data-testid="audit-panel" data-job={jobId}>
      <span>{initialJob.name}</span>
      <button type="button" onClick={() => onJobChange({ ...initialJob, name: 'renamed by audit' })}>
        audit-change
      </button>
    </div>
  ),
}));
vi.mock('@/components/features/cron/BlueprintCatalog', () => ({
  default: ({ onSelect }: { onSelect: (blueprint: { id: string }) => void }) => (
    <button type="button" onClick={() => onSelect({ id: 'daily' })}>
      pick-blueprint
    </button>
  ),
}));
vi.mock('@/components/features/cron/BlueprintInlineFill', () => ({
  default: ({ blueprint, onBack, onCreated }: InlineFillProps) => (
    <div data-testid="inline-fill" data-blueprint={blueprint.id}>
      <button type="button" onClick={onBack}>
        blueprint-back
      </button>
      <button type="button" onClick={() => onCreated(createdJobOf('blueprint-job'))}>
        blueprint-created
      </button>
    </div>
  ),
}));
vi.mock('@/components/features/cron/CronDeployModeNotice', () => ({
  default: () => <div data-testid="deploy-notice" />,
}));

interface AuditPanelProps {
  jobId: string;
  initialJob: CronJob;
  onJobChange: (job: CronJob) => void;
}

interface InlineFillProps {
  blueprint: { id: string };
  onBack: () => void;
  onCreated: (job: CronJob) => void;
}

export interface DialogProps {
  open?: boolean;
  presetChatId?: string | null;
  presetChatTitle?: string | null;
}

export { elapse, settle, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

export const state = hoisted.state;
export const toast = hoisted.toast;
export const fetchAgents: Mock = hoisted.fetchAgents;
export const createJob: Mock = hoisted.createJob;
export const prepareAudit: Mock = hoisted.prepareAudit;
export const checkCronPrerequisite: Mock = hoisted.checkCronPrerequisite;
export const listChannelStatuses: Mock = hoisted.listChannelStatuses;
export const fetchWorkflowTemplates: Mock = hoisted.fetchWorkflowTemplates;
export const apiRequest: Mock = hoisted.apiRequest;

export function prerequisiteOf(satisfied: boolean): PrerequisiteCheckResponse {
  return {
    fingerprint: 'fp',
    manual_success_count: satisfied ? 3 : 1,
    threshold: 3,
    is_satisfied: satisfied,
    chat_verified_count: 0,
    kanban_verified_count: 0,
    override_allowed: true,
  };
}

export function createdJobOf(id: string, fields: Partial<CronJob> = {}): CronJob {
  return { id, name: id, status: 'active', ...fields } as CronJob;
}

export function templateOf(
  id: string,
  displayName: string,
  placeholders: string[] = [],
  trustLatch = true,
): WorkflowTemplateSummary {
  return {
    template_id: id,
    display_name: displayName,
    script_hash: `hash-${id}`,
    trust_latch: trustLatch,
    required_agent_types: [],
    placeholders,
    is_trunk: false,
    created_at: '2030-01-01T00:00:00Z',
    updated_at: '2030-01-01T00:00:00Z',
  };
}

/** Fresh fixtures: local deployment, no agents / chats / channels / templates, every request succeeds. */
export function resetKit(): void {
  vi.clearAllMocks();
  state.agents = [];
  state.providerPrimary = null;
  state.chats = [];
  state.canDismissAudit = true;
  apiRequest.mockResolvedValue({ deploy_mode: 'local' });
  listChannelStatuses.mockResolvedValue([]);
  fetchWorkflowTemplates.mockResolvedValue({ templates: [] });
  checkCronPrerequisite.mockRejectedValue(new Error('no prerequisite data'));
  createJob.mockImplementation(async () => createdJobOf('job-1'));
  prepareAudit.mockImplementation(async (job: CronJob) => job);
}

const pointer = () =>
  userEvent.setup({
    advanceTimers: (ms) => {
      if (vi.isFakeTimers()) {
        vi.advanceTimersByTime(ms);
      }
    },
  });

export const click = async (element: Element) => {
  fireEvent.click(element);
  await settle();
};

export const typeInto = async (element: Element, value: string) => {
  fireEvent.change(element, { target: { value } });
  await settle();
};

export const button = (name: string): HTMLElement => screen.getByRole('button', { name });
export const radio = (name: string): HTMLElement => screen.getByRole('radio', { name });
export const placeholder = (text: string): HTMLElement => screen.getByPlaceholderText(text);
/** The select whose trigger currently shows `shown` (Radix renders the selected item's text in the trigger). */
export const combo = (shown: string): HTMLElement => {
  const found = screen.getAllByRole('combobox').find((element) => element.textContent === shown);
  if (!found) {
    throw new Error(`no select currently showing "${shown}"`);
  }
  return found;
};

/** Opens a select menu the way a pointer does, so a following `pickOption` behaves like a real selection. */
export async function openSelect(trigger: HTMLElement): Promise<void> {
  await pointer().click(trigger);
  await settle();
}

/** Picks an option of the select menu that is already open. */
export async function pickOption(option: string): Promise<void> {
  await pointer().click(await screen.findByRole('option', { name: option }));
  await settle();
  await waitFor(() => expect(screen.queryByRole('listbox')).toBeNull());
}

export async function choose(trigger: HTMLElement, option: string): Promise<void> {
  await openSelect(trigger);
  await pickOption(option);
}

export interface OpenedDialog {
  onOpenChange: Mock;
  view: RenderResult;
}

export async function openDialog(props: DialogProps = {}): Promise<OpenedDialog> {
  const onOpenChange = vi.fn();
  const view = render(<CronJobCreateDialog open onOpenChange={onOpenChange} {...props} />);
  await settle();
  return { onOpenChange, view };
}

/** The parent changes `open` (and what the dialog is opened for) without the dialog being dismissed from inside. */
export async function setDialogOpen(
  { view, onOpenChange }: OpenedDialog,
  open: boolean,
  props: Omit<DialogProps, 'open'> = {},
): Promise<void> {
  view.rerender(<CronJobCreateDialog open={open} onOpenChange={onOpenChange} {...props} />);
  await settle();
}

export async function openCustom(props: DialogProps = {}): Promise<OpenedDialog> {
  const opened = await openDialog(props);
  await click(screen.getByTestId('cron-create-mode-custom'));
  return opened;
}

/** Custom tab with an agent prompt and a daily schedule — the smallest form that can be submitted. */
export async function fillValidJob(props: DialogProps = {}): Promise<OpenedDialog> {
  const opened = await openCustom(props);
  await typeInto(placeholder('createPromptPlaceholder'), 'Summarise the news');
  await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
  return opened;
}

export const submit = () => click(button('createSubmit'));

/** The request body of the only `createJob` call. */
export function sentPayload(): CreateCronJobRequest {
  expect(createJob).toHaveBeenCalledTimes(1);
  return createJob.mock.calls[0]?.[0] as CreateCronJobRequest;
}
