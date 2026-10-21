import type { ProgressItem } from '@/store/chat/types/progress';

import { baseName, trunc } from './pathUtils';

export type HumanizeContext = {
  filename?: string;
  query?: string;
  url?: string;
  command?: string;
  description?: string;
  text?: string;
  target?: string;
  skillName?: string;
  action?: string;
  mcpServer?: string;
  mcpTool?: string;
};

function readStringField(input: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = input[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
  }
  return undefined;
}

export function extractContextFromToolInput(input: Record<string, unknown>): HumanizeContext {
  const path = readStringField(input, ['path', 'file_path', 'filePath', 'target_path']);
  const command = readStringField(input, ['command', 'code']);
  const description = readStringField(input, ['description', 'reason', 'execution_intent']);
  const query = readStringField(input, ['query', 'search_query', 'pattern']);
  const url = readStringField(input, ['url', 'href']);
  const target = readStringField(input, ['target', 'channel', 'recipient']);
  const skillName = readStringField(input, ['name', 'skill_name']);
  const action = readStringField(input, ['action']);
  const text = readStringField(input, ['text', 'content', 'message']);

  return {
    filename: path ? baseName(path) : undefined,
    query: query ? trunc(query, 60) : undefined,
    url: url ? trunc(url, 50) : undefined,
    command: command ? trunc(command, 60) : undefined,
    description,
    text: text ? trunc(text, 70) : undefined,
    target,
    skillName,
    action,
  };
}

function firstRecord(items: ProgressItem['items']): Record<string, unknown> | undefined {
  if (!Array.isArray(items) || items.length === 0) {
    return undefined;
  }
  const first = items[0];
  return first && typeof first === 'object' ? (first as Record<string, unknown>) : undefined;
}

export function extractContextFromProgressStep(step: ProgressItem): HumanizeContext {
  const ctx: HumanizeContext = {};

  if (step.reason && step.reason.trim()) {
    ctx.description = trunc(step.reason.trim(), 80);
  }

  const { items } = step;
  const first = firstRecord(items);
  if (first && typeof first.file_path === 'string') {
    ctx.filename = baseName(first.file_path);
  } else if (first && typeof first.query === 'string') {
    ctx.query = trunc(first.query, 60);
  } else if (first && typeof first.pattern === 'string') {
    ctx.query = trunc(first.pattern, 60);
  } else if (first && typeof first.url === 'string') {
    ctx.url = trunc(first.url, 50);
  } else if (first && typeof first.text === 'string') {
    ctx.text = trunc(first.text, 70);
  } else if (first && typeof first.code === 'string') {
    ctx.command = trunc(first.code, 60);
  } else if (typeof items === 'string' && items.trim()) {
    ctx.text = trunc(items.trim(), 70);
  }

  return ctx;
}

export function parseMcpToolName(toolName: string): { server?: string; tool?: string } {
  if (!toolName.startsWith('mcp__')) {
    return {};
  }
  const parts = toolName.split('__').filter(Boolean);
  if (parts.length < 3) {
    return { tool: parts[parts.length - 1] };
  }
  return {
    server: parts[1],
    tool: parts.slice(2).join('__'),
  };
}
