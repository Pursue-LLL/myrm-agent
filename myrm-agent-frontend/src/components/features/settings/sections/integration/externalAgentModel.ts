/**
 * [INPUT]
 * - @/services/config::ExternalAgentConfig (POS: one stored external agent entry)
 *
 * [OUTPUT]
 * - DEFAULT_AGENT, AGENT_PRESETS: the blank entry and the one-click presets of the add form
 * - PERMISSION_MODE_OPTIONS, PERMISSION_MODE_HINTS, normalizePermissionMode: the modes each backend type can honour
 * - backendKeyFromCommand: command → known login backend
 * - ExternalAgentDraft, EnvRow, toDraft, newEnvRow, envRowProblems, cleanAgent: the editable form of an agent
 *   and the rules for turning it back into what is stored
 *
 * [POS]
 * Pure data and rules of the external agent editor; no React, so every rule is unit-testable.
 */

import type { ExternalAgentConfig, ExternalAgentPermissionMode, ExternalAgentType } from '@/services/config';

export const DEFAULT_AGENT: ExternalAgentConfig = {
  name: '',
  type: 'cli',
  command: '',
  args: [],
  enabled: true,
  permissionMode: 'safe',
  authMode: 'subscription',
  description: '',
  maxTurns: 25,
};

/** Map a CLI command to its known auth backend key (codex/claude/gemini/qwen). */
const KNOWN_BACKENDS = ['codex', 'claude', 'gemini', 'qwen'] as const;
export function backendKeyFromCommand(command: string): string | null {
  const base = (command.split(/[\\/]/).pop() ?? '').toLowerCase().split('.')[0];
  if (KNOWN_BACKENDS.includes(base as (typeof KNOWN_BACKENDS)[number])) {
    return base;
  }
  return KNOWN_BACKENDS.find((b) => base.includes(b)) ?? null;
}

export const AGENT_PRESETS: { key: string; config: ExternalAgentConfig }[] = [
  {
    key: 'claude',
    config: {
      ...DEFAULT_AGENT,
      name: 'claude-code',
      command: 'claude',
      args: ['-p', '--output-format', 'stream-json'],
      description: 'Full-stack coding agent powered by Anthropic Claude',
    },
  },
  {
    key: 'codex',
    config: {
      ...DEFAULT_AGENT,
      name: 'codex-cli',
      command: 'codex',
      args: ['exec', '--json'],
      description: 'OpenAI Codex CLI coding agent (requires Responses API provider)',
    },
  },
  {
    key: 'gemini',
    config: {
      ...DEFAULT_AGENT,
      name: 'gemini-cli',
      command: 'gemini',
      args: ['--output-format', 'stream-json'],
      description: 'Google Gemini-powered coding agent',
    },
  },
];

/**
 * Permission modes each backend can actually honour. CLI backends receive fixed
 * command-line flags, while ACP backends get their permission requests answered by the
 * bridge on the user's behalf. Neither exposes an interactive prompt today, so no
 * backend may advertise one.
 */
export const PERMISSION_MODE_OPTIONS: Record<
  ExternalAgentType,
  { value: ExternalAgentPermissionMode; labelKey: string }[]
> = {
  cli: [
    { value: 'allow_all', labelKey: 'permissionAllowAll' },
    { value: 'safe', labelKey: 'permissionSafe' },
  ],
  acp: [
    { value: 'allow_all', labelKey: 'permissionAllowAll' },
    { value: 'safe', labelKey: 'permissionSafe' },
  ],
};

export const PERMISSION_MODE_HINTS: Record<ExternalAgentType, string> = {
  cli: 'permissionHintCli',
  acp: 'permissionHintAcp',
};

/** Coerce a stored mode to one the given backend type can honour (fallback: fail-closed). */
export function normalizePermissionMode(
  type: ExternalAgentType,
  mode: ExternalAgentPermissionMode,
): ExternalAgentPermissionMode {
  return PERMISSION_MODE_OPTIONS[type].some((option) => option.value === mode) ? mode : 'safe';
}

/** One line of the environment editor. Blank and unfinished lines exist only while the form is open. */
export interface EnvRow {
  id: string;
  name: string;
  value: string;
}

/** An agent being edited: its environment is a list of lines, so a line being typed can be shown as it is. */
export type ExternalAgentDraft = Omit<ExternalAgentConfig, 'env'> & { envRows: EnvRow[] };

let nextEnvRowId = 0;

export function newEnvRow(name = '', value = ''): EnvRow {
  nextEnvRowId += 1;
  return { id: `env-row-${nextEnvRowId}`, name, value };
}

export function toDraft(agent: ExternalAgentConfig): ExternalAgentDraft {
  const { env, ...rest } = agent;
  return { ...rest, envRows: Object.entries(env ?? {}).map(([name, value]) => newEnvRow(name, value)) };
}

export type EnvRowProblem = 'missing' | 'invalid' | 'duplicate';

// A name outside this shape cannot be put into a process environment: spawning the agent fails on it.
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

const isBlankRow = (row: EnvRow): boolean => row.name.trim() === '' && row.value === '';

/** What is wrong with each line, by row id. A blank line is left out of the agent and is never wrong. */
export function envRowProblems(rows: readonly EnvRow[]): Map<string, EnvRowProblem> {
  const problems = new Map<string, EnvRowProblem>();
  const taken = new Set<string>();
  for (const row of rows) {
    if (isBlankRow(row)) {
      continue;
    }
    const name = row.name.trim();
    if (!name) {
      problems.set(row.id, 'missing');
    } else if (!ENV_NAME.test(name)) {
      problems.set(row.id, 'invalid');
    } else if (taken.has(name)) {
      problems.set(row.id, 'duplicate');
    } else {
      taken.add(name);
    }
  }
  return problems;
}

/**
 * The agent as it is stored: trimmed text, no blank arguments, a permission mode its type can honour
 * (otherwise switching type could persist a mode the form never showed), and an `env` only when it has
 * entries. The environment lines must have passed `envRowProblems`.
 */
export function cleanAgent(draft: ExternalAgentDraft): ExternalAgentConfig {
  const { envRows, ...rest } = draft;
  const env = Object.fromEntries(envRows.filter((row) => !isBlankRow(row)).map((row) => [row.name.trim(), row.value]));
  const cleaned: ExternalAgentConfig = {
    ...rest,
    name: draft.name.trim(),
    command: draft.command.trim(),
    args: (draft.args ?? []).filter((a) => a.trim() !== ''),
    permissionMode: normalizePermissionMode(draft.type, draft.permissionMode),
  };
  if (Object.keys(env).length > 0) {
    cleaned.env = env;
  }
  return cleaned;
}
