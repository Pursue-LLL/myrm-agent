/**
 * [INPUT]
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 *
 * [OUTPUT]
 * - KNOWN_RULE_FILENAMES, isKnownRuleFileName, computeStringHash,
 *   computeCombinedHash, diffRuleFiles, formatReloadToastMessage, dispatchRulesReloadEvent
 *
 * [POS]
 * Pure computation engine for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite.
 * Calculates content hashes, validates rule file identifiers, computes structural diffs,
 * formats status toasts, and broadcasts zero-restart cache invalidation events.
 */

import type {
  WorkspaceRuleFile,
  RulesReloadSource,
  RuleFileDiff,
  RulesReloadEventPayload,
} from './rulesHotReloadTypes';

export const KNOWN_RULE_FILENAMES: readonly string[] = [
  'AGENTS.md',
  'CLAUDE.md',
  'append-system.md',
  '.cursorrules',
  '.windsurfrules',
  'SYSTEM.md',
];

export function isKnownRuleFileName(filename: string): boolean {
  const normalized = filename.trim().toLowerCase();
  return KNOWN_RULE_FILENAMES.some((known) => known.toLowerCase() === normalized);
}

export function computeStringHash(content: string): string {
  let hash = 2166136261;
  for (let i = 0; i < content.length; i++) {
    hash ^= content.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

export function computeCombinedHash(files: readonly WorkspaceRuleFile[]): string {
  if (files.length === 0) {
    return '00000000';
  }

  const sortedSignatures = [...files]
    .sort((a, b) => a.filename.localeCompare(b.filename))
    .map((f) => `${f.filename}:${f.hash}`)
    .join('|');

  return computeStringHash(sortedSignatures);
}

export function diffRuleFiles(
  prevFiles: readonly WorkspaceRuleFile[],
  nextFiles: readonly WorkspaceRuleFile[],
): readonly RuleFileDiff[] {
  const diffs: RuleFileDiff[] = [];
  const prevMap = new Map(prevFiles.map((f) => [f.filename, f]));
  const nextMap = new Map(nextFiles.map((f) => [f.filename, f]));

  // 检查新增与变更
  for (const nextFile of nextFiles) {
    const prevFile = prevMap.get(nextFile.filename);
    if (!prevFile) {
      diffs.push({
        filename: nextFile.filename,
        diffType: 'added',
        currentHash: nextFile.hash,
      });
    } else if (prevFile.hash !== nextFile.hash) {
      diffs.push({
        filename: nextFile.filename,
        diffType: 'modified',
        previousHash: prevFile.hash,
        currentHash: nextFile.hash,
      });
    }
  }

  // 检查已删除
  for (const prevFile of prevFiles) {
    if (!nextMap.has(prevFile.filename)) {
      diffs.push({
        filename: prevFile.filename,
        diffType: 'removed',
        previousHash: prevFile.hash,
      });
    }
  }

  return diffs;
}

export function formatReloadToastMessage(
  diffs: readonly RuleFileDiff[],
  source: RulesReloadSource,
): string {
  if (diffs.length === 0) {
    if (source === 'manual_reload' || source === 'slash_command') {
      return '工作区规则已校验，未发现文件变更。';
    }
    return '工作区规则状态正常。';
  }

  const summaryParts = diffs.map((d) => {
    const actionLabel =
      d.diffType === 'added' ? '新增' : d.diffType === 'modified' ? '已修改' : '已移除';
    return `${d.filename} (${actionLabel})`;
  });

  return `工作区规则已热更新：${summaryParts.join('、')}，免重启即刻生效。`;
}

export function dispatchRulesReloadEvent(payload: RulesReloadEventPayload): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const event = new CustomEvent('myrm:workspace-rules-reloaded', {
      detail: payload,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    return true;
  } catch {
    return false;
  }
}
