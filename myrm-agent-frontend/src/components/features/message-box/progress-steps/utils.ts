/**
 * ProgressSteps 工具函数
 */

import React from 'react';

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

/**
 * 获取语义化的工具标签
 * @param tool_name 工具名称
 * @param t 翻译函数
 * @returns 语义化标签，如果没有映射则返回格式化的工具名
 */
export const getSemanticToolLabel = (tool_name: string, t: TranslateFn): string => {
  // 尝试获取i18n翻译
  const translationKey = `toolSemanticLabels.${tool_name}`;
  const translated = t(translationKey);

  // 如果翻译存在且不是key本身，使用翻译
  if (translated && translated !== translationKey) {
    return translated;
  }

  // MCP prefixed tools (mcp__{server}__{tool}): extract tool part for display
  if (tool_name.startsWith('mcp__')) {
    const parts = tool_name.split('__');
    const toolPart = parts.length >= 3 ? parts.slice(2).join('__') : parts[parts.length - 1];
    return toolPart
      .replace(/_tool$/, '')
      .replace(/_/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // 否则格式化工具名
  return tool_name
    .replace(/_tool$/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * 根据 step_key 获取步骤标题
 * @param step 步骤信息
 * @param t 翻译函数
 * @param useSemantic 是否使用语义化标签（默认true）
 * @returns 步骤标题
 */
export const getStepTitle = (step: ProgressItem, t: TranslateFn, useSemantic: boolean = true): string => {
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

  // 验证 step_key 格式
  const isValidStepKey =
    step_key && step_key.length <= 50 && !step_key.includes('\n') && !/[\u4e00-\u9fff]/.test(step_key);

  // 尝试直接获取翻译
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

  // delegation_xxx_status → 提取 agent 名称
  if (step_key?.startsWith('delegation_') && step_key.endsWith('_status')) {
    const agentName = step_key.slice('delegation_'.length, -'_status'.length);
    try {
      return t('delegation', { agentName });
    } catch {
      return `Delegating to ${agentName}`;
    }
  }

  // 使用 tool_name，优先使用语义化标签
  const validToolName = tool_name && tool_name.length <= 50 && !tool_name.includes('\n');
  if (validToolName) {
    // 如果启用语义化且有映射，使用语义化标签（通过i18n）
    const toolLabel = useSemantic
      ? getSemanticToolLabel(tool_name, t)
      : tool_name
          .replace(/_tool$/, '')
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());

    let baseTitle = toolLabel;

    // 如果有耗时数据（心跳），追加显示
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
  if (!isValidUrl) return;

  let finalUrl = url;
  if (url.startsWith('www.')) {
    finalUrl = `https://${url}`;
  }

  window.open(finalUrl, '_blank', 'noopener,noreferrer');
};
