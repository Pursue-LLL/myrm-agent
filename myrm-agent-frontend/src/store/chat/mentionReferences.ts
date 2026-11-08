/**
 * [INPUT]
 * @/store/useAgentStore::useAgentStore (POS: Agent catalog store, resolves inline @agent tokens)
 * ./inSessionMentionDeduplicator (POS: Per-chat record of the files already injected)
 *
 * [OUTPUT]
 * buildMentionPayload: The request fields a turn's mention references become.
 * extractInlineMentionReferences: Parse @token references typed into the input text.
 * isReferenceTokenAlive: Whether a menu-selected reference is still present in the input text.
 * mergeMentionReferences: Merge selected and inline references without duplicates.
 * truncateSelectionContent: Cap selection snippets to the server's inline budget.
 *
 * [POS]
 * Mention reference rules of the message request: what the user typed and selected becomes the request's references.
 */

import type { StreamRequestBody } from '@/services/chat';
import type { MentionReference, MentionReferenceType } from '@/store/chat/types';
import useAgentStore from '../useAgentStore';
import type { ChatActionsState } from './chatActions';
import { inSessionMentionDeduplicator } from './inSessionMentionDeduplicator';

const LINE_RANGE_REFERENCE_PATTERN = /^@(.+):(\d+)(?:-(\d+))?$/;
// Selection snippets must stay under the server's 100KB per-part inline budget:
// 32_000 chars * 3 bytes (worst-case UTF-8) = 96KB, so selections always inline
// instead of tripping the protocol's field cap or the too-large degradation path.
const SELECTION_CONTENT_MAX_CHARS = 32_000;
const SELECTION_TRUNCATION_SUFFIX = '\n…[truncated]';

export function truncateSelectionContent(content: string): string {
  if (content.length <= SELECTION_CONTENT_MAX_CHARS) {
    return content;
  }
  return `${content.slice(0, SELECTION_CONTENT_MAX_CHARS)}${SELECTION_TRUNCATION_SUFFIX}`;
}

const mentionReferenceKey = (reference: MentionReference) =>
  `${reference.type}:${reference.path ?? reference.fileId ?? reference.url ?? reference.label}:${reference.startLine ?? ''}:${reference.endLine ?? ''}`;

export const extractInlineMentionReferences = (input: string): MentionReference[] => {
  const references: MentionReference[] = [];
  for (const token of input.match(/@\S+/g) ?? []) {
    if (token === '@staged') {
      references.push({ type: 'git_staged', label: '@staged', source: 'special', size: null });
    } else if (token === '@diff') {
      references.push({ type: 'git_diff', label: '@diff', source: 'special', size: null });
    } else if (token === '@codebase') {
      references.push({ type: 'codebase', label: '@codebase', source: 'special', size: null });
    } else if (token.startsWith('@folder:') && token.length > '@folder:'.length) {
      const path = token.slice('@folder:'.length);
      references.push({ type: 'workspace_folder', label: token, path, source: 'workspace', size: null });
    } else if (token.startsWith('@url:') && token.length > '@url:'.length) {
      const url = token.slice('@url:'.length);
      references.push({ type: 'url', label: token, url, source: 'special', size: null });
    } else if (token.startsWith('@wiki:') && token.length > '@wiki:'.length) {
      const conceptName = token.slice('@wiki:'.length);
      references.push({
        type: 'wiki_concept',
        label: token,
        conceptName,
        source: 'wiki',
        size: null,
      });
    } else {
      const lineMatch = LINE_RANGE_REFERENCE_PATTERN.exec(token);
      if (!lineMatch) {
        const cleanName = token.slice(1).toLowerCase();
        if (cleanName) {
          const agents = useAgentStore.getState().agents;
          const matched = agents.find((a) => a.id.toLowerCase() === cleanName || a.name.toLowerCase() === cleanName);
          if (matched) {
            references.push({
              type: 'agent',
              label: token,
              fileId: matched.id,
              source: 'agent',
              size: null,
            });
          }
        }
        continue;
      }
      const [, path, startRaw, endRaw] = lineMatch;
      let startLine = Number(startRaw);
      let endLine = endRaw ? Number(endRaw) : startLine;
      if (!Number.isSafeInteger(startLine) || !Number.isSafeInteger(endLine)) {
        continue;
      }
      if (endLine < startLine) {
        [startLine, endLine] = [endLine, startLine];
      }
      references.push({
        type: 'workspace_file',
        label: token,
        path,
        startLine,
        endLine,
        source: 'workspace',
        size: null,
      });
    }
  }
  return references;
};

/**
 * 判断「通过输入框文本 @token 添加」（@ 菜单选中）的引用是否仍以文本形式存在。
 *
 * 仅对 `viaText` 引用生效：`selectReference` 写入输入框的 @token 与 store 引用字段一一对应，
 * 用户若直接删除引用文本（而非点击引用 chip 的 ×），store 引用会残留，
 * 提交前据此过滤，保证「文本有 @xxx → 生效；没有 → 不生效」语义一致，
 * 避免 @agent 意外委派、@wiki/@chat 意外注入。
 * 文件浏览器/全局搜索/拖拽/research 等非文本入口添加的引用不参与过滤。
 */
export const isReferenceTokenAlive = (reference: MentionReference, input: string): boolean => {
  if (!reference.viaText) {
    return true;
  }
  switch (reference.type) {
    case 'agent':
      // toMentionReference 生成的 label 已带 @ 前缀（如 '@研究专家'），直接整体匹配文本 token
      return input.includes(reference.label);
    case 'wiki_concept':
      return reference.conceptName ? input.includes(`@wiki:${reference.conceptName}`) : input.includes('@wiki:');
    case 'prior_chat':
      return input.includes(reference.label);
    case 'workspace_folder':
      return Boolean(reference.path) && input.includes(`@folder:${reference.path}`);
    case 'workspace_file':
      return Boolean(reference.path) && input.includes(`@${reference.path}`);
    case 'url':
      return Boolean(reference.url) && input.includes(`@url:${reference.url}`);
    case 'git_staged':
      return input.includes('@staged');
    case 'git_diff':
      return input.includes('@diff');
    case 'codebase':
      return input.includes('@codebase');
    default:
      // uploaded_file / generated_file / wiki_raw_file 等非文本 token 引用，不参与文本过滤
      return true;
  }
};

export const mergeMentionReferences = (
  selected: MentionReference[],
  inline: MentionReference[],
): MentionReference[] => {
  const seen = new Set<string>();
  const merged: MentionReference[] = [];
  for (const reference of [...selected, ...inline]) {
    const key = mentionReferenceKey(reference);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(reference);
  }
  return merged;
};

/**
 * The request fields a turn's mention references become: file-like references (a file already injected into this
 * chat is sent again without its content) and the ids of the mentioned agents.
 */
export const buildMentionPayload = (
  state: Pick<ChatActionsState, 'chatId' | 'mentionReferences'>,
  input: string,
): Pick<StreamRequestBody, 'mention_references' | 'mentioned_agent_ids'> => {
  const references = mergeMentionReferences(
    state.mentionReferences.filter((r) => isReferenceTokenAlive(r, input)),
    extractInlineMentionReferences(input),
  );
  if (references.length === 0) {
    return {};
  }

  const fileReferences = references.filter(
    (r): r is Omit<MentionReference, 'type'> & { type: Exclude<MentionReferenceType, 'agent'> } => r.type !== 'agent',
  );
  const agentReferences = references.filter((r) => r.type === 'agent');

  // Partition fresh vs redundant files in current session
  const effectiveChatId = state.chatId ?? '';
  const { fresh, redundant } = inSessionMentionDeduplicator.partitionMentions(effectiveChatId, fileReferences);
  const redundantPaths = new Set(
    redundant
      .map((r) => inSessionMentionDeduplicator.normalizePath(r.path ?? r.label.replace(/^@/, '')))
      .filter(Boolean),
  );

  // Register newly injected files in session deduplicator
  const freshPaths = fresh.map((r) => r.path ?? r.label.replace(/^@/, '')).filter((p): p is string => Boolean(p));
  if (freshPaths.length > 0 && effectiveChatId) {
    inSessionMentionDeduplicator.markInjected(effectiveChatId, freshPaths);
  }

  const payload: Pick<StreamRequestBody, 'mention_references' | 'mentioned_agent_ids'> = {};
  if (fileReferences.length > 0) {
    payload.mention_references = fileReferences.map((reference) => {
      const normPath = inSessionMentionDeduplicator.normalizePath(reference.path ?? reference.label.replace(/^@/, ''));
      const isRedundantInSession = redundantPaths.has(normPath);
      const shouldOmitContent = isRedundantInSession && Boolean(reference.content);

      return {
        type: reference.type,
        path: reference.path,
        file_id: reference.fileId,
        url: reference.url,
        label: reference.label,
        start_line: reference.startLine,
        end_line: reference.endLine,
        ...(reference.conceptName ? { concept_name: reference.conceptName } : {}),
        ...(reference.range ? { range: reference.range } : {}),
        ...(reference.content && !shouldOmitContent ? { content: truncateSelectionContent(reference.content) } : {}),
      };
    });
  }
  if (agentReferences.length > 0) {
    payload.mentioned_agent_ids = agentReferences.map((r) => r.fileId).filter((id): id is string => id !== undefined);
  }
  return payload;
};
