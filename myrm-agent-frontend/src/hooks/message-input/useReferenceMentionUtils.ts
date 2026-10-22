/**
 * [INPUT]
 * - @/services/chat::{ReferenceSuggestion, ReferenceSuggestionSource, SearchResult} (POS: 引用项契约)
 * - @/store/chat/types::MentionReference (POS: Store 引用契约)
 * - @/store/useAgentStore (POS: 获取本地已加载数字员工列表)
 * - @/components/agent/builtin-agent-i18n::getBuiltinAgentName (POS: 数字员工多语言名称)
 *
 * [OUTPUT]
 * - ReferenceMentionState: 引用自动补全内部状态类型
 * - DEBOUNCE_MS: 防抖时延常量
 * - extractMentionQuery: 提取光标前 @ 提及词
 * - staticSpecialMatches: 静态特殊命令匹配
 * - historyResultToSuggestion: 历史会话引用转换
 * - toMentionReference: 建议项转 Store 引用实体
 * - replacementFor: 建议项转输入框替换文本
 * - buildAgentSuggestions: 检索并构建本地数字员工建议项
 *
 * [POS]
 * useReferenceMention 的无状态纯逻辑与工具集，保证 EmptyChat 下首屏秒级 @Agent 唤起与三端同构。
 */

import type { ReferenceSuggestion, ReferenceSuggestionSource, SearchResult } from '@/services/chat';
import type { MentionReference } from '@/store/chat/types';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

export interface ReferenceMentionState {
  isOpen: boolean;
  results: ReferenceSuggestion[];
  selectedIndex: number;
  query: string;
  mentionStart: number;
}

export const DEBOUNCE_MS = 180;

export const STATIC_SPECIAL_RESULTS: ReferenceSuggestion[] = [
  {
    source: 'special',
    reference_type: 'git_staged',
    kind: 'reference',
    label: '@staged',
    basename: '@staged',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Git staged changes',
    size: null,
    score_tier: 'prefix',
    score: 1000,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'git_diff',
    kind: 'reference',
    label: '@diff',
    basename: '@diff',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Git working tree changes',
    size: null,
    score_tier: 'prefix',
    score: 990,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'workspace_folder',
    kind: 'directory',
    label: '@folder:',
    basename: '@folder:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Directory tree under workspace',
    size: null,
    score_tier: 'prefix',
    score: 980,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'url',
    kind: 'reference',
    label: '@url:',
    basename: '@url:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Fetch webpage content',
    size: null,
    score_tier: 'prefix',
    score: 970,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'wiki_concept',
    kind: 'reference',
    label: '@wiki:',
    basename: '@wiki:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Knowledge base concept',
    size: null,
    score_tier: 'prefix',
    score: 960,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'prior_chat',
    kind: 'reference',
    label: '@chat:',
    basename: '@chat:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Reference a prior conversation',
    size: null,
    score_tier: 'prefix',
    score: 950,
    match_ranges: [],
  },
];

export function extractMentionQuery(text: string, cursorPos: number): { query: string; start: number } | null {
  const before = text.slice(0, cursorPos);
  const atIndex = before.lastIndexOf('@');
  if (atIndex === -1) {
    return null;
  }
  if (atIndex > 0 && /\S/.test(before[atIndex - 1])) {
    return null;
  }

  const query = before.slice(atIndex + 1);
  if (query.includes('\n') || query.includes(' ')) {
    return null;
  }
  return { query, start: atIndex };
}

export function staticSpecialMatches(query: string): ReferenceSuggestion[] {
  const lowerQuery = query.toLowerCase();
  return STATIC_SPECIAL_RESULTS.filter((item) => {
    const token = item.basename.replace(/^@/, '').replace(/:$/, '').toLowerCase();
    return !lowerQuery || token.startsWith(lowerQuery);
  });
}

export function buildAgentSuggestions(query: string, locale: string): ReferenceSuggestion[] {
  const agents = useAgentStore.getState().agents;
  const lowerQuery = query.toLowerCase();
  return agents
    .filter((a) => {
      if (!lowerQuery) {
        return true;
      }
      const localized = getBuiltinAgentName(a.id, a.name, locale);
      return (
        a.name.toLowerCase().includes(lowerQuery) ||
        localized.toLowerCase().includes(lowerQuery) ||
        a.id.toLowerCase().includes(lowerQuery)
      );
    })
    .map((a) => {
      const localized = getBuiltinAgentName(a.id, a.name, locale);
      return {
        source: 'agent',
        reference_type: 'agent',
        kind: 'agent',
        label: localized,
        basename: localized,
        directory: a.description || 'Agent',
        relative_path: null,
        file_id: a.id,
        description: a.description || null,
        size: null,
        score_tier: 'prefix',
        score: 2000,
        match_ranges: [],
        avatar_url: a.avatar_url,
      };
    });
}

export function historyResultToSuggestion(item: SearchResult): ReferenceSuggestion {
  const title = item.chat_title?.trim() || 'Untitled conversation';
  return {
    source: (item.source || 'special') as ReferenceSuggestionSource,
    reference_type: 'prior_chat',
    kind: 'reference',
    label: `@chat:${title}`,
    basename: title,
    directory: item.snippet?.slice(0, 120) || '',
    relative_path: item.chat_id,
    file_id: item.chat_id,
    description: item.snippet?.slice(0, 160) || null,
    size: null,
    score_tier: 'content',
    score: 800,
    match_ranges: [],
  };
}

export function toMentionReference(item: ReferenceSuggestion): MentionReference | null {
  if (item.reference_type === 'prior_chat') {
    const chatId = item.file_id ?? item.relative_path;
    if (!chatId) {
      return null;
    }
    return {
      type: 'prior_chat',
      label: item.label.startsWith('@') ? item.label : `@chat:${item.basename}`,
      path: chatId,
      fileId: chatId,
      source: 'special',
      size: null,
    };
  }
  if (item.reference_type === 'agent') {
    return {
      type: 'agent',
      label: item.label.startsWith('@') ? item.label : `@${item.label}`,
      path: undefined,
      fileId: item.file_id ?? undefined,
      source: 'agent',
      size: null,
      directory: item.directory || undefined,
    };
  }
  if (item.reference_type === 'url' && !item.label.startsWith('@url:http')) {
    return null;
  }
  if (item.reference_type === 'workspace_folder' && !item.relative_path) {
    return null;
  }
  if (item.reference_type === 'wiki_concept' && !item.concept_name) {
    return null;
  }
  const label = item.label.startsWith('@') ? item.label : `@${item.basename || item.label}`;
  return {
    type: item.reference_type,
    label,
    path: item.relative_path ?? undefined,
    fileId: item.file_id ?? undefined,
    url: item.reference_type === 'url' ? item.label.replace(/^@url:/, '') : undefined,
    source: item.source as MentionReference['source'],
    size: item.size,
    directory: item.directory || undefined,
    conceptName: item.concept_name ?? undefined,
  };
}

export function replacementFor(item: ReferenceSuggestion, folderMode: boolean): string {
  if (item.reference_type === 'agent') {
    const name = item.label.startsWith('@') ? item.label.slice(1) : item.label;
    return `@${name} `;
  }
  if (item.reference_type === 'git_staged') {
    return '@staged ';
  }
  if (item.reference_type === 'git_diff') {
    return '@diff ';
  }
  if (item.reference_type === 'url') {
    return '@url:';
  }
  if (item.reference_type === 'workspace_folder') {
    if (item.relative_path) {
      return `@folder:${item.relative_path} `;
    }
    return '@folder:';
  }
  if (item.reference_type === 'wiki_concept') {
    if (item.concept_name) {
      return `@wiki:${item.concept_name} `;
    }
    return '@wiki:';
  }
  if (item.reference_type === 'prior_chat') {
    if (item.file_id) {
      return `@chat:${item.basename} `;
    }
    return '@chat:';
  }
  if (folderMode && item.relative_path) {
    return `@folder:${item.relative_path} `;
  }
  return `@${item.relative_path ?? item.label} `;
}
