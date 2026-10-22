/**
 * Service orchestrating controlled fabrication detection, placeholder replacement, and fact verification.
 * Adheres to WorkBuddy fact verification paradigm with zero emojis.
 */

import {
  FactCheckAuditReport,
  PlaceholderItem,
  VerifiedFactItem,
} from './factCheckTypes';

export class FactCheckService {
  /**
   * Parse content to extract placeholders matching [待替换占位: xxx] or {{placeholder:xxx}}.
   */
  public static parsePlaceholders(content: string): PlaceholderItem[] {
    const placeholders: PlaceholderItem[] = [];
    if (!content) {
      return placeholders;
    }

    // Match [待替换占位: xxx] or [待替换占位：xxx] or {{placeholder:xxx}}
    const regex = /(?:\[待替换占位[:：]\s*([^\]]+)\])|(?:\{\{placeholder[:：]\s*([^}]+)\}\})/g;
    let match: RegExpExecArray | null = regex.exec(content);
    let idCounter = 1;

    while (match !== null) {
      const originalText = match[0];
      const placeholderKey = (match[1] || match[2] || '').trim();
      const matchIndex = match.index;

      // Extract 35-char snippet around the match
      const start = Math.max(0, matchIndex - 35);
      const end = Math.min(content.length, matchIndex + originalText.length + 35);
      const snippetPrefix = start > 0 ? '...' : '';
      const snippetSuffix = end < content.length ? '...' : '';
      const contextSnippet = `${snippetPrefix}${content.substring(start, end).replace(/\n+/g, ' ')}${snippetSuffix}`;

      placeholders.push({
        id: `ph-${idCounter++}`,
        originalText,
        placeholderKey,
        contextSnippet,
        status: 'pending',
        index: matchIndex,
      });

      match = regex.exec(content);
    }

    return placeholders;
  }

  /**
   * Replace a specific placeholder with user-provided verified benchmark value.
   */
  public static replacePlaceholder(
    content: string,
    placeholderId: string,
    realValue: string,
    placeholders: PlaceholderItem[]
  ): { updatedContent: string; updatedPlaceholders: PlaceholderItem[] } {
    const target = placeholders.find((p) => p.id === placeholderId);
    if (!target) {
      return { updatedContent: content, updatedPlaceholders: placeholders };
    }

    // Replace first occurrence of target.originalText
    const updatedContent = content.replace(target.originalText, realValue);

    const updatedPlaceholders = placeholders.map((p) => {
      if (p.id === placeholderId) {
        return {
          ...p,
          status: 'replaced' as const,
          replacedValue: realValue,
        };
      }
      return p;
    });

    return { updatedContent, updatedPlaceholders };
  }

  /**
   * Replace all pending placeholders with provided key-value mappings.
   */
  public static replaceAllPlaceholders(
    content: string,
    replacements: Record<string, string>,
    placeholders: PlaceholderItem[]
  ): { updatedContent: string; updatedPlaceholders: PlaceholderItem[] } {
    let updatedContent = content;
    const updatedPlaceholders: PlaceholderItem[] = [];

    for (const p of placeholders) {
      const realVal = replacements[p.id];
      if (realVal && realVal.trim()) {
        updatedContent = updatedContent.replace(p.originalText, realVal.trim());
        updatedPlaceholders.push({
          ...p,
          status: 'replaced',
          replacedValue: realVal.trim(),
        });
      } else {
        updatedPlaceholders.push(p);
      }
    }

    return { updatedContent, updatedPlaceholders };
  }

  /**
   * Parse structured verified facts metadata or heuristic citation blocks.
   */
  public static parseVerifiedFacts(
    factsMetadata?: VerifiedFactItem[]
  ): VerifiedFactItem[] {
    if (factsMetadata && factsMetadata.length > 0) {
      return factsMetadata;
    }
    return [];
  }

  /**
   * Build complete audit report from content and verified facts metadata.
   */
  public static auditContent(
    content: string,
    verifiedFacts?: VerifiedFactItem[]
  ): FactCheckAuditReport {
    const placeholders = this.parsePlaceholders(content);
    const facts = this.parseVerifiedFacts(verifiedFacts);
    const pendingCount = placeholders.filter((p) => p.status === 'pending').length;
    const replacedCount = placeholders.filter((p) => p.status === 'replaced').length;

    return {
      totalPlaceholders: placeholders.length,
      pendingCount,
      replacedCount,
      placeholders,
      verifiedFacts: facts,
      hasFabrications: pendingCount > 0,
    };
  }
}
