import type { Source } from '@/store/chat/types';
import { resolveSourceClickUrl } from '@/store/chat/types/sources';
import { maskCodeRegions, unmaskCodeRegions } from './maskCodeRegions';

const CITATION_FULLWIDTH_RE = /\u3010(\d+)\u3011/g;
const CITATION_FULLWIDTH_FW_DIGIT_RE = /\u3010([\uFF10-\uFF19]+)\u3011/g;
const CITATION_HALFWIDTH_RE = /\[(\d+)\](?!\()/g;
const CITATION_MARKDOWN_LINK_RE = /\[citation:([^\]]*)\]\(([^)]+)\)/gi;

const normalizeCitationIndexDigits = (numStr: string): string =>
  numStr.replace(/[\uFF10-\uFF19]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xff10 + 0x30)).trim();

const escapeHtmlAttr = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const buildCitationTag = (numStr: string, sources: Source[]): string => {
  const normalizedNumStr = normalizeCitationIndexDigits(numStr);
  const num = parseInt(normalizedNumStr, 10);
  if (!Number.isFinite(num) || num <= 0) {
    return `[${numStr}]`;
  }

  let sourceIndex = sources.findIndex((s) => Number(s.index) === num);
  if (sourceIndex === -1 && num <= sources.length) {
    sourceIndex = num - 1;
  }
  if (sourceIndex === -1) {
    return `[${numStr}]`;
  }
  const source = sources[sourceIndex];
  const safeUrl = escapeHtmlAttr(resolveSourceClickUrl(source) || source?.url || '');
  return `<citation data-num="${normalizedNumStr}" data-source-index="${sourceIndex}" data-url="${safeUrl}"></citation>`;
};

const findSourceIndexByUrl = (url: string, sources: Source[]): number =>
  sources.findIndex((source) => {
    const candidate = resolveSourceClickUrl(source) || source.url || '';
    return candidate === url;
  });

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

  processed = processed.replace(CITATION_FULLWIDTH_RE, (_match, numStr: string) =>
    buildCitationTag(numStr, sources),
  );

  processed = processed.replace(CITATION_FULLWIDTH_FW_DIGIT_RE, (_match, numStr: string) =>
    buildCitationTag(numStr, sources),
  );

  processed = processed.replace(CITATION_HALFWIDTH_RE, (_match, numStr: string) =>
    buildCitationTag(numStr, sources),
  );

  return processed;
};

/** Convert inline citation markers into `<citation>` tags for MarkdownContent. */
export const preprocessCitationMarkers = (text: string, sources: Source[]): string => {
  if (sources.length === 0) {
    return text;
  }

  const { text: maskedText, slots } = maskCodeRegions(text);
  const processed = applyCitationReplacements(maskedText, sources);
  return unmaskCodeRegions(processed, slots);
};
