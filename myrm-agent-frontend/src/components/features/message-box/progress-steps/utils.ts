/**
 * ProgressSteps 工具函数
 */

import React from 'react';

import { humanizeProgressStep } from '@/lib/humanize';
import type { TranslateFn as HumanizeTranslateFn } from '@/lib/humanize';
import type { ProgressItem } from '@/store/useChatStore';
import { getStepCategory } from './toolIcons';

const URL_SPLIT_RE = /(https?:\/\/[^\s)]+)/g;

/**
 * Split text into plain-text and URL segments, returning React nodes.
 * Plain text is auto-escaped by React; URLs render as clickable <a> tags.
 */
export function linkifyErrorText(text: string): React.ReactNode[] {
  const parts = text.split(URL_SPLIT_RE);
  return parts.map((part, i) =>
    part.startsWith('http://') || part.startsWith('https://')
      ? React.createElement(
          'a',
          {
            key: i,
            href: part,
            target: '_blank',
            rel: 'noopener noreferrer',
            className: 'text-blue-600 dark:text-blue-400 hover:underline',
          },
          part,
        )
      : part,
  );
}

// 来源项类型定义
export interface SourceItem {
  index: number;
  type: string;
  url?: string;
  title?: string;
  snippet?: string;
}

// 技能选择项类型定义
export interface SkillSelectItem {
  skill_name: string;
  reason?: string;
}

// 类型判断函数
export const isTextItems = (items: unknown): items is { text: string }[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.text === 'string';
};

export const isQueryItems = (items: unknown): items is { query: string }[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.query === 'string';
};

export const isUrlItems = (items: unknown): items is { url: string }[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.url === 'string';
};

export const isTextString = (items: unknown): items is string => {
  return typeof items === 'string';
};

export const isSourceItems = (items: unknown): items is SourceItem[] => {
  return (
    Array.isArray(items) &&
    items.length > 0 &&
    typeof items[0]?.index === 'number' &&
    typeof items[0]?.type === 'string'
  );
};

export const isSkillSelectItems = (items: unknown): items is SkillSelectItem[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.skill_name === 'string';
};

// 文件路径项类型定义
export interface FilePathItem {
  file_path: string;
  line_range?: string;
  action_type?: string;
  size_bytes?: string;
  diff?: string;
  diff_truncated?: boolean;
}

export const isFilePathItems = (items: unknown): items is FilePathItem[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.file_path === 'string';
};

export interface SearchToolItem {
  pattern: string;
  search_path?: string;
  file_pattern?: string;
  cached?: boolean;
  cache_age_seconds?: number;
  saved_tokens?: number;
  scenario?: 'realtime' | 'standard' | 'archive';
}

export const isSearchToolItems = (items: unknown): items is SearchToolItem[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.pattern === 'string';
};

// 代码项类型定义
export interface CodeItem {
  code: string;
}

export const isCodeItems = (items: unknown): items is CodeItem[] => {
  return Array.isArray(items) && items.length > 0 && typeof items[0]?.code === 'string';
};

// 翻译函数类型 - 兼容 next-intl 的 Translator 类型
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TranslateFn = (key: string, values?: any) => string;

/**
 * 推断当前步骤的宏观阶段（用于折叠状态显示）
 * @param step 步骤信息
 * @param t 翻译函数
 * @returns 宏观阶段标签
 */
export const inferStageLabel = (step: ProgressItem, t: TranslateFn): string => {
  const { tool_name, step_key } = step;

  if (step_key === 'analyzing_image') {
    return t('analyzing_image');
  }

  // 获取步骤类别
  const category = getStepCategory(step_key, tool_name);

  // 返回对应的宏观阶段标签（使用i18n翻译）
  return t(`categoryStageLabels.${category}`);
};

// `delegation_<agent>_<kind>` steps of a delegation to an external agent: its status line, one of its tool calls,
// or a notice that the conversation it had earlier did not continue.
const DELEGATION_STEP_RE = /^delegation_(.+)_(status|tool|session_expired|session_workspace_changed)$/;

type DelegationKind = 'status' | 'tool' | 'session_expired' | 'session_workspace_changed';

const parseDelegationStep = (stepKey: string | undefined): { agentName: string; kind: DelegationKind } | null => {
  const match = stepKey ? DELEGATION_STEP_RE.exec(stepKey) : null;
  return match ? { agentName: match[1], kind: match[2] as DelegationKind } : null;
};

/** A delegated tool call is one line ("claude: Read — note.txt") that already is the step's title, so the body has nothing to add. */
export const isDelegationToolLine = (step: ProgressItem): boolean =>
  parseDelegationStep(step.step_key)?.kind === 'tool' && isTextItems(step.items);

/**
 * 根据 step_key 获取步骤标题
 * @param step 步骤信息
 * @param t 翻译函数
 * @param useSemantic 是否使用语义化标签（默认true）
 * @returns 步骤标题
 */
export const getStepTitle = (
  step: ProgressItem,
  t: TranslateFn,
  useSemantic: boolean = true,
  tHumanize?: HumanizeTranslateFn,
): string => {
  const { step_key, tool_name, is_plan, items } = step;

  if (is_plan && items && isTextItems(items) && items.length > 0) {
    return items[0].text;
  }

  // ``ptc_notify:<category>`` inline activity cards render their most recent
  // notify message as title; category becomes a sub-label badge if present.
  if (step_key?.startsWith('ptc_notify:')) {
    if (step.notify_message) {
      return step.notify_message;
    }
    const category = step_key.slice('ptc_notify:'.length);
    return category === 'default' ? t('processing') || 'Processing...' : category;
  }

  if (step_key?.startsWith('workflow_stage:')) {
    if (step.notify_message) {
      return step.notify_message;
    }
    const category = step_key.slice('workflow_stage:'.length);
    return category === 'default' ? t('workflow_stage') || 'Workflow stage update' : category;
  }

  const delegation = parseDelegationStep(step_key);
  if (delegation) {
    const { agentName, kind } = delegation;
    if (kind === 'tool') {
      if (isTextItems(items)) {
        return items[0].text;
      }
    } else if (kind === 'status') {
      try {
        return t('delegation', { agentName });
      } catch {
        return `Delegating to ${agentName}`;
      }
    } else {
      return t(`delegation_${kind}`, { agentName });
    }
  }

  const validToolName = tool_name && tool_name.length <= 50 && !tool_name.includes('\n');

  // Tool steps: args-aware humanize wins over generic step_key labels (e.g. file_write_tool → "Writing file")
  if (validToolName && useSemantic && tHumanize) {
    const humanized = humanizeProgressStep(step, tHumanize);
    if (humanized) {
      let baseTitle = humanized;
      if (step.elapsed_ms && step.status !== 'success' && step.status !== 'error') {
        const seconds = Math.floor(step.elapsed_ms / 1000);
        baseTitle = `${baseTitle} (${seconds}s)`;
      }
      return baseTitle;
    }
  }

  // 验证 step_key 格式
  const isValidStepKey =
    step_key && step_key.length <= 50 && !step_key.includes('\n') && !/[\u4e00-\u9fff]/.test(step_key);

  // 尝试直接获取翻译（非工具步骤，如 context_compaction / analyzing_image）
  if (isValidStepKey) {
    try {
      const translation = step.count !== undefined ? t(step_key, { count: step.count }) : t(step_key);
      const isMissing = !translation || translation === step_key || translation.endsWith(step_key);
      if (!isMissing) {
        return translation;
      }
    } catch {
      // 继续尝试其他方式
    }
  }

  // 使用 tool_name 格式化 fallback
  if (validToolName) {
    let baseTitle = tool_name
      .replace(/_tool$/, '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());

    if (step.elapsed_ms && step.status !== 'success' && step.status !== 'error') {
      const seconds = Math.floor(step.elapsed_ms / 1000);
      baseTitle = `${baseTitle} (${seconds}s)`;
    }

    return baseTitle;
  }

  // 返回通用文案
  if (!isValidStepKey) {
    return t('processing') || 'Processing...';
  }

  // 格式化 step_key
  return step_key
    .replace(/_tool$/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * 处理链接点击
 */
export const handleLinkClick = (url: string, isValidUrl: boolean): void => {
  if (!isValidUrl) {
    return;
  }

  let finalUrl = url;
  if (url.startsWith('www.')) {
    finalUrl = `https://${url}`;
  }

  window.open(finalUrl, '_blank', 'noopener,noreferrer');
};
