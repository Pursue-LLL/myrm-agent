import type { Source } from '@/store/chat/types';
import { resolveSourceClickUrl } from '@/store/chat/types/sources';
import { maskCodeRegions, unmaskCodeRegions } from './maskCodeRegions';

const CITATION_MARKDOWN_LINK_RE =
  /(?<!!)\[citation:\s*([^\]]*?)\]\((https?:\/\/(?:[^\s()]|\([^\s()]*\))+)\)/gi;
const CITATION_BRACKET_RE = /(?:【|［|〔|\[)([\d\uFF10-\uFF19\s,，、\-~－]+)(?:】|］|〕|\])(?!\()/g;
const UNSUPPORTED_CITATION_CONTROL_MARKER_RE = /[\uE200-\uE203]cite(?:[\uE200-\uE203][^\uE200-\uE203]*)?[\uE200-\uE203]/g;
const TRAILING_UNSUPPORTED_CITATION_CONTROL_MARKER_RE = /[ \t]*[\uE200-\uE203]cite(?:[\uE200-\uE203][^\uE200-\uE203]*)?[\uE200-\uE203](?=\r?\n|$)/g;

const GENERIC_CITATION_TITLES = new Set(['source', '来源', 'untitled', 'link', '网页']);

/** Normalize citation title, falling back to clean domain when generic or empty. */
export const normalizeCitationTitle = (title: string, url?: string): string => {
  const compact = title.replace(/\s+/g, ' ').trim();
  if (!compact || GENERIC_CITATION_TITLES.has(compact.toLowerCase())) {
    if (url) {
      try {
        return new URL(url).hostname.replace(/^www\./i, '');
      } catch {
        // fallback to compact
      }
    }
    return compact || 'Source';
  }
  return compact;
};

/** Strip unsupported private Unicode citation control tokens emitted by certain LLMs. */
export const stripUnsupportedCitationControlMarkers = (text: string): string =>
  text
    .replace(TRAILING_UNSUPPORTED_CITATION_CONTROL_MARKER_RE, '')
    .replace(UNSUPPORTED_CITATION_CONTROL_MARKER_RE, '');

const normalizeCitationDigits = (s: string): string =>
  s.replace(/[\uFF10-\uFF19]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xff10 + 0x30)).trim();

const escapeHtmlAttr = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const expandCitationIndices = (rawInner: string): number[] => {
  const normalized = normalizeCitationDigits(rawInner);
  const rangeMatch = /^(\d+)\s*[-~－]\s*(\d+)$/.exec(normalized);
  if (rangeMatch && rangeMatch[1] && rangeMatch[2]) {
    const start = parseInt(rangeMatch[1], 10);
    const end = parseInt(rangeMatch[2], 10);
    if (Number.isFinite(start) && Number.isFinite(end) && start > 0 && end >= start && end - start <= 20) {
      const res: number[] = [];
      for (let i = start; i <= end; i++) {
        res.push(i);
      }
      return res;
    }
  }

  const parts = normalized.split(/[,，、\s]+/).filter(Boolean);
  const res: number[] = [];
  for (const part of parts) {
    const num = parseInt(part, 10);
    if (Number.isFinite(num) && num > 0) {
      res.push(num);
    }
  }
  return res;
};

const buildCitationTagForNumber = (num: number, sources: Source[]): string => {
  let sourceIndex = sources.findIndex((s) => Number(s.index) === num);
  if (sourceIndex === -1 && num <= sources.length) {
    sourceIndex = num - 1;
  }
  if (sourceIndex === -1) {
    return `[${num}]`;
  }
  const source = sources[sourceIndex];
  const safeUrl = escapeHtmlAttr(resolveSourceClickUrl(source) || source?.url || '');
  return `<citation data-num="${num}" data-source-index="${sourceIndex}" data-url="${safeUrl}"></citation>`;
};

const findSourceIndexByUrl = (url: string, sources: Source[]): number =>
  sources.findIndex((source) => {
    const candidate = resolveSourceClickUrl(source) || source.url || '';
    return candidate === url;
  });

const processBracketMatch = (match: string, innerText: string, sources: Source[]): string => {
  const indices = expandCitationIndices(innerText);
  if (indices.length === 0) {
    return match;
  }

  const hasAnyValid = indices.some((num) => {
    const idx = sources.findIndex((s) => Number(s.index) === num);
    return idx !== -1 || (num <= sources.length && num > 0);
  });

  if (!hasAnyValid) {
    return match;
  }

  return indices.map((num) => buildCitationTagForNumber(num, sources)).join('');
};

const applyCitationReplacements = (text: string, sources: Source[]): string => {
  let processed = text.replace(CITATION_MARKDOWN_LINK_RE, (match, _title: string, url: string) => {
    const sourceIndex = findSourceIndexByUrl(url, sources);
    if (sourceIndex === -1) {
      return match;
    }
    const source = sources[sourceIndex];
    const numStr = String(source?.index ?? sourceIndex + 1);
    const safeUrl = escapeHtmlAttr(url);
    return `<citation data-num="${numStr}" data-source-index="${sourceIndex}" data-url="${safeUrl}"></citation>`;
  });

  processed = processed.replace(CITATION_BRACKET_RE, (match, innerText: string) =>
    processBracketMatch(match, innerText, sources),
  );

  return processed;
};

/** Convert inline citation markers into `<citation>` tags for MarkdownContent. */
export const preprocessCitationMarkers = (text: string, sources: Source[]): string => {
  const sanitized = stripUnsupportedCitationControlMarkers(text);
  if (sources.length === 0) {
    return sanitized;
  }

  const { text: maskedText, slots } = maskCodeRegions(sanitized);
  const processed = applyCitationReplacements(maskedText, sources);
  return unmaskCodeRegions(processed, slots);
};
