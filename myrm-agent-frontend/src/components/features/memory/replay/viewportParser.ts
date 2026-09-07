/**
 * [INPUT]
 * - raw prompt_preview string from TraceLLMCall / event_log (POS: Formatted as `[role] content\n...`)
 *
 * [OUTPUT]
 * - parseModelViewport: Parse structured viewport items from prompt preview
 * - ParsedViewportMessage, ViewportInspectionSummary types
 *
 * [POS]
 * Model viewport parser for Session Replay & Execution Trace v2.
 * Pure utility function to transform flattened LLM prompt previews into
 * structured, role-segregated inspectable cards without data mutation.
 */

export type ViewportRole = 'system' | 'user' | 'assistant' | 'tool' | 'other';

export interface ParsedViewportMessage {
  id: string;
  role: ViewportRole;
  content: string;
  isTruncated?: boolean;
}

export interface ViewportInspectionSummary {
  messages: ParsedViewportMessage[];
  totalMessages: number;
  hasSystemPrompt: boolean;
  userMessageCount: number;
  toolCallCount: number;
  isGloballyTruncated: boolean;
  truncatedCharsCount: number;
}

const ROLE_HEADER_REGEX = /^\[(system|user|assistant|tool|[^\]]+)\]\s*(.*)$/is;
const TRUNCATED_FOOTER_REGEX = /\.\.\.\s*\[truncated\s+(\d+)\s+chars\]$/i;

/**
 * Parses raw prompt_preview text into structured viewport messages.
 */
export function parseModelViewport(previewText: string | null | undefined): ViewportInspectionSummary {
  if (!previewText || typeof previewText !== 'string' || !previewText.trim()) {
    return {
      messages: [],
      totalMessages: 0,
      hasSystemPrompt: false,
      userMessageCount: 0,
      toolCallCount: 0,
      isGloballyTruncated: false,
      truncatedCharsCount: 0,
    };
  }

  let text = previewText.trim();
  let isGloballyTruncated = false;
  let truncatedCharsCount = 0;

  const truncateMatch = text.match(TRUNCATED_FOOTER_REGEX);
  if (truncateMatch) {
    isGloballyTruncated = true;
    truncatedCharsCount = parseInt(truncateMatch[1], 10) || 0;
    text = text.replace(TRUNCATED_FOOTER_REGEX, '').trimEnd();
  }

  // Split text by role boundaries: \n[role]
  const lines = text.split('\n');
  const messages: ParsedViewportMessage[] = [];
  let currentRole: ViewportRole = 'other';
  let currentBuffer: string[] = [];
  let itemCounter = 0;

  const flushBuffer = () => {
    if (currentBuffer.length > 0 || currentRole !== 'other') {
      const content = currentBuffer.join('\n').trim();
      messages.push({
        id: `vp-msg-${itemCounter++}`,
        role: currentRole,
        content,
      });
      currentBuffer = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Check if line starts a new message block like "[system] ..." or "[user] ..."
    const headerMatch = line.match(/^\[([a-zA-Z0-9_-]+)\](?:\s*(.*))?$/);
    if (headerMatch) {
      flushBuffer();
      const rawRole = headerMatch[1].toLowerCase();
      if (rawRole === 'system') {
        currentRole = 'system';
      } else if (rawRole === 'user') {
        currentRole = 'user';
      } else if (rawRole === 'assistant') {
        currentRole = 'assistant';
      } else if (rawRole === 'tool' || rawRole === 'tool_calls') {
        currentRole = 'tool';
      } else {
        currentRole = 'other';
      }

      const initialContent = headerMatch[2] ?? '';
      if (initialContent.trim().length > 0) {
        currentBuffer.push(initialContent);
      }
    } else {
      currentBuffer.push(line);
    }
  }

  flushBuffer();

  const hasSystemPrompt = messages.some((m) => m.role === 'system');
  const userMessageCount = messages.filter((m) => m.role === 'user').length;
  const toolCallCount = messages.filter((m) => m.role === 'tool').length;

  return {
    messages,
    totalMessages: messages.length,
    hasSystemPrompt,
    userMessageCount,
    toolCallCount,
    isGloballyTruncated,
    truncatedCharsCount,
  };
}
