/**
 * [INPUT] @/services/cron.types (POS: 创建请求 / 调度 / 任务类型), @/lib/utils/cronEstimate (POS: 月度执行次数估算), ../CronDeliveryEditors::toApiChannel (POS: 投递渠道到 API 渠道), ../cron-utils::parseTimeoutSeconds (POS: 运行时间上限解析)
 * [OUTPUT] CronCreateDraft / initialDraft: 创建弹窗全部可重置状态；buildSchedule / estimateMonthlyExecutions: 由草稿推导调度与月度执行次数；hasContent / defaultTaskName / prerequisiteQuery / appliesTimeout / isTimeoutInputValid / isSessionValid: 草稿校验与派生；buildDeliveryPayload / buildCreatePayload: 草稿到创建请求
 * [POS] 创建弹窗的纯逻辑层（无 React）：状态形状、校验与请求体都在这里，由 useCronCreateForm 与各字段组件消费，可独立单测。
 */

import type { CreateCronJobRequest, CronJob, CronSchedule, SessionTarget } from '@/services/cron.types';
import { estimateCronMonthlyExecutions, estimateIntervalMonthlyExecutions } from '@/lib/utils/cronEstimate';
import type { CronBlueprint } from '../cron-blueprints';
import { toApiChannel } from '../CronDeliveryEditors';
import { parseTimeoutSeconds } from '../cron-utils';

/** What the user picks as the kind of job; a script is stored as a `router` job. */
export type UIJobMode = 'agent' | 'shell' | 'script' | 'reminder';
export type ScheduleKind = CronSchedule['kind'];
export type DraftSessionTarget = Extract<SessionTarget, 'isolated' | 'main'>;
export type CreateMode = 'template' | 'custom';

export interface CriterionDraft {
  type: string;
  description: string;
}

/** Select value for "the default agent" / "no workflow template"; neither is sent to the server. */
export const DEFAULT_AGENT_ID = '__default__';
export const NO_WORKFLOW_TEMPLATE = '__none__';
export const MIN_INTERVAL_MINUTES = 5;
export const MAX_ACCEPTANCE_CRITERIA = 10;

/** Everything the dialog holds that closing it throws away. */
export interface CronCreateDraft {
  createMode: CreateMode;
  selectedBlueprint: CronBlueprint | null;
  createdJob: CronJob | null;
  uiMode: UIJobMode;
  name: string;
  prompt: string;
  command: string;
  scriptCode: string;
  agentId: string;
  scheduleKind: ScheduleKind;
  cronExpr: string;
  intervalMinutes: string;
  onceAt: string;
  sessionTarget: DraftSessionTarget;
  selectedChatId: string;
  deliveryChannel: string;
  deliveryTarget: string;
  acceptanceCriteria: CriterionDraft[];
  timeoutSeconds: string;
  workflowTemplateId: string;
  workflowTemplateArgs: Record<string, string> | null;
  workflowArgsDialogOpen: boolean;
  overridePrerequisite: boolean;
}

/** A dialog opened for one chat starts bound to that chat's thread. */
export function initialDraft(presetChatId?: string | null): CronCreateDraft {
  return {
    createMode: 'template',
    selectedBlueprint: null,
    createdJob: null,
    uiMode: 'agent',
    name: '',
    prompt: '',
    command: '',
    scriptCode: '',
    agentId: DEFAULT_AGENT_ID,
    scheduleKind: 'cron',
    cronExpr: '',
    intervalMinutes: '',
    onceAt: '',
    sessionTarget: presetChatId ? 'main' : 'isolated',
    selectedChatId: '',
    deliveryChannel: 'chat',
    deliveryTarget: '',
    acceptanceCriteria: [],
    timeoutSeconds: '',
    workflowTemplateId: NO_WORKFLOW_TEMPLATE,
    workflowTemplateArgs: null,
    workflowArgsDialogOpen: false,
    overridePrerequisite: false,
  };
}

type ScheduleFields = Pick<CronCreateDraft, 'scheduleKind' | 'cronExpr' | 'intervalMinutes' | 'onceAt'>;

/** Whole minutes of a repeat interval, or null when the input is not a number the scheduler accepts. */
function parseIntervalMinutes(raw: string): number | null {
  const minutes = parseInt(raw, 10);
  return !minutes || minutes < MIN_INTERVAL_MINUTES ? null : minutes;
}

/** The schedule the inputs describe, or null while they are incomplete or invalid. */
export function buildSchedule(fields: ScheduleFields, tz: string): CronSchedule | null {
  switch (fields.scheduleKind) {
    case 'cron': {
      const expr = fields.cronExpr.trim();
      return expr ? { kind: 'cron', expr, tz } : null;
    }
    case 'interval': {
      const minutes = parseIntervalMinutes(fields.intervalMinutes);
      return minutes === null ? null : { kind: 'interval', interval_ms: minutes * 60_000, tz };
    }
    case 'once': {
      const at = fields.onceAt.trim();
      if (!at) {
        return null;
      }
      const date = new Date(at);
      return Number.isNaN(date.getTime()) ? null : { kind: 'once', run_at: date.toISOString() };
    }
  }
}

/** Runs per month the schedule implies; null when it cannot be estimated. */
export function estimateMonthlyExecutions(fields: Omit<ScheduleFields, 'onceAt'>): number | null {
  switch (fields.scheduleKind) {
    case 'cron': {
      const expr = fields.cronExpr.trim();
      return expr ? estimateCronMonthlyExecutions(expr) : null;
    }
    case 'interval': {
      const minutes = parseIntervalMinutes(fields.intervalMinutes);
      return minutes === null ? null : estimateIntervalMonthlyExecutions(minutes * 60_000);
    }
    case 'once':
      return 1;
  }
}

type ContentFields = Pick<CronCreateDraft, 'uiMode' | 'prompt' | 'command' | 'scriptCode'>;

/** Which input holds the text of each kind of job. */
const CONTENT_FIELD = {
  agent: 'prompt',
  reminder: 'prompt',
  shell: 'command',
  script: 'scriptCode',
} as const satisfies Record<UIJobMode, keyof ContentFields>;

function activeContent(draft: ContentFields): string {
  return draft[CONTENT_FIELD[draft.uiMode]];
}

export function hasContent(draft: ContentFields): boolean {
  return activeContent(draft).trim().length > 0;
}

/** The name the user typed, or the first words of the job's text. */
export function defaultTaskName(draft: ContentFields & Pick<CronCreateDraft, 'name'>): string {
  return draft.name.trim() || activeContent(draft).trim().slice(0, 30);
}

/** What a prerequisite check is asked about: kinds that run a prompt send it, the others send their command. */
export function prerequisiteQuery(draft: ContentFields): { prompt: string; command: string } {
  const { uiMode } = draft;
  return {
    prompt: uiMode === 'agent' || uiMode === 'reminder' ? draft.prompt : '',
    command: uiMode === 'shell' ? draft.command : uiMode === 'script' ? draft.scriptCode : '',
  };
}

/** A reminder is delivered at once and has no limit to set. */
export function appliesTimeout(uiMode: UIJobMode): boolean {
  return uiMode !== 'reminder';
}

/** Empty keeps the server default; a typed limit must be one the server accepts. */
export function isTimeoutInputValid(uiMode: UIJobMode, raw: string): boolean {
  return !appliesTimeout(uiMode) || raw.trim() === '' || parseTimeoutSeconds(raw) !== null;
}

/** A job bound to a thread needs the chat it belongs to. */
export function isSessionValid(sessionTarget: DraftSessionTarget, chatId: string | null): boolean {
  return sessionTarget === 'isolated' || chatId !== null;
}

/** Delivering into the chat is the default and sends nothing; any other channel goes with its optional recipient. */
export function buildDeliveryPayload(channel: string, target: string): CreateCronJobRequest['delivery'] {
  if (channel === 'chat') {
    return undefined;
  }
  const recipient = target.trim();
  return { channel: toApiChannel(channel), ...(recipient ? { target: recipient } : {}) };
}

function toJobType(uiMode: UIJobMode): CreateCronJobRequest['job_type'] {
  return uiMode === 'script' ? 'router' : uiMode;
}

interface CreatePayloadInput {
  draft: CronCreateDraft;
  schedule: CronSchedule;
  /** The chat a thread-bound job belongs to. */
  chatId: string | null;
  /** Values for the placeholders of the selected workflow template. */
  workflowArgs: Record<string, string> | null;
}

export function buildCreatePayload({
  draft,
  schedule,
  chatId,
  workflowArgs,
}: CreatePayloadInput): CreateCronJobRequest {
  const { uiMode, sessionTarget } = draft;
  const payload: CreateCronJobRequest = {
    name: defaultTaskName(draft),
    job_type: toJobType(uiMode),
    schedule,
    session_target: sessionTarget,
    ...(sessionTarget === 'main' && chatId ? { chat_id: chatId } : {}),
  };

  if (uiMode === 'shell') {
    payload.command = draft.command.trim();
  } else if (uiMode === 'script') {
    payload.pre_condition_script = draft.scriptCode.trim();
  } else {
    payload.prompt = draft.prompt.trim();
  }

  if (uiMode === 'agent') {
    if (draft.agentId !== DEFAULT_AGENT_ID) {
      payload.agent_id = draft.agentId;
    }
    if (draft.workflowTemplateId !== NO_WORKFLOW_TEMPLATE) {
      payload.workflow_template_id = draft.workflowTemplateId;
      if (workflowArgs && Object.keys(workflowArgs).length > 0) {
        payload.workflow_template_args = workflowArgs;
      }
    }
  }

  const delivery = buildDeliveryPayload(draft.deliveryChannel, draft.deliveryTarget);
  if (delivery) {
    payload.delivery = delivery;
  }

  const criteria = draft.acceptanceCriteria
    .filter((criterion) => criterion.description.trim())
    .map((criterion) => ({ type: criterion.type, description: criterion.description.trim() }));
  if (criteria.length > 0) {
    payload.acceptance_criteria = criteria;
  }

  const timeout = appliesTimeout(uiMode) ? parseTimeoutSeconds(draft.timeoutSeconds) : null;
  if (timeout !== null) {
    payload.timeout_seconds = timeout;
  }

  if (draft.overridePrerequisite) {
    payload.override_prerequisite = true;
  }
  return payload;
}
