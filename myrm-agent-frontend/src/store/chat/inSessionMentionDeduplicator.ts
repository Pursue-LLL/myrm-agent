/**
 * [INPUT]
 * - store/chat/types::MentionReference (POS: Chat mention reference models.)
 *
 * [OUTPUT]
 * - inSessionMentionDeduplicator: session-scoped tracker and deduplicator for @-mention injected files,
 *   preventing redundant full-text token bloat across turns.
 *
 * [POS]
 * In-session mention lifecycle guardian ensuring files injected in earlier turns
 * are not redundantly packed into subsequent prompts.
 */

import type { MentionReference } from '@/store/chat/types';

export interface InjectedFileMeta {
  normalizedPath: string;
  originalPath: string;
  injectedAtMs: number;
  turnIndex: number;
}

class InSessionMentionDeduplicator {
  // chatId -> Map<normalizedPath, InjectedFileMeta>
  private sessionRegistry = new Map<string, Map<string, InjectedFileMeta>>();

  public normalizePath(path: string): string {
    return path.trim().replace(/\\/g, '/').replace(/^\/+/, '');
  }

  public isPathInjected(chatId: string, rawPath: string): boolean {
    if (!chatId || !rawPath) {
      return false;
    }
    const registry = this.sessionRegistry.get(chatId);
    if (!registry) {
      return false;
    }
    const normalized = this.normalizePath(rawPath);
    return registry.has(normalized);
  }

  public getInjectedPaths(chatId: string): string[] {
    const registry = this.sessionRegistry.get(chatId);
    if (!registry) {
      return [];
    }
    return Array.from(registry.values()).map((meta) => meta.originalPath);
  }

  public markInjected(chatId: string, rawPaths: string[], turnIndex = 0): void {
    if (!chatId || rawPaths.length === 0) {
      return;
    }
    let registry = this.sessionRegistry.get(chatId);
    if (!registry) {
      registry = new Map<string, InjectedFileMeta>();
      this.sessionRegistry.set(chatId, registry);
    }

    const now = Date.now();
    for (const path of rawPaths) {
      if (!path) {
        continue;
      }
      const normalized = this.normalizePath(path);
      if (!registry.has(normalized)) {
        registry.set(normalized, {
          normalizedPath: normalized,
          originalPath: path,
          injectedAtMs: now,
          turnIndex,
        });
      }
    }
  }

  public clearSession(chatId: string): void {
    this.sessionRegistry.delete(chatId);
  }

  public clearAll(): void {
    this.sessionRegistry.clear();
  }

  /**
   * Partitions mention references into:
   * - fresh: files not yet injected in the current session (eligible for direct full content injection)
   * - redundant: files already present in session context (skipped from re-injecting full content, only citation kept)
   */
  public partitionMentions(
    chatId: string,
    references: readonly MentionReference[],
  ): {
    fresh: MentionReference[];
    redundant: MentionReference[];
  } {
    const fresh: MentionReference[] = [];
    const redundant: MentionReference[] = [];

    for (const ref of references) {
      const targetPath = ref.path ?? ref.label.replace(/^@/, '');
      // Only workspace / file references are subject to session file deduplication
      const isFileLike =
        ref.type === 'workspace_file' ||
        ref.type === 'uploaded_file' ||
        ref.type === 'generated_file' ||
        ref.source === 'workspace';

      if (isFileLike && targetPath && this.isPathInjected(chatId, targetPath)) {
        redundant.push(ref);
      } else {
        fresh.push(ref);
      }
    }

    return { fresh, redundant };
  }
}

export const inSessionMentionDeduplicator = new InSessionMentionDeduplicator();
