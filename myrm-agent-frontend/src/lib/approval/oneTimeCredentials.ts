/**
 * [INPUT]
 * - @/lib/api::API_BASE_URL (POS: 后端基础地址)
 *
 * [OUTPUT]
 * - stageOneTimeCredentials: 为审批卡上展示的那一条命令暂存一次性凭据，返回 handle 引用
 * - wipeOneTimeCredentials: 立即销毁已暂存的凭据（撤回、拒绝、命令被改写）
 * - OneTimeCredentialError: 服务端拒绝时抛出，带 HTTP 状态与服务端说明
 * - supportsOneTimeCredentials: 哪个工具的审批卡可以录入一次性凭据
 * - BLOCKED_CREDENTIAL_KEYS: 不允许作为凭据名的系统环境变量（预检，权威校验在服务端）
 *
 * [POS]
 * 一次性凭据的 HTTP 客户端。凭据按 chat 与命令文本绑定；明文只经此处发往服务端内存，不进入任何前端 store。
 */

import { API_BASE_URL } from '@/lib/api';

/** Mirrors harness `validate_credential_key`: names that would let a credential hijack the shell. */
export const BLOCKED_CREDENTIAL_KEYS: ReadonlySet<string> = new Set([
  'BASH_ENV',
  'DYLD_INSERT_LIBRARIES',
  'DYLD_LIBRARY_PATH',
  'ENV',
  'HOME',
  'IFS',
  'LD_LIBRARY_PATH',
  'LD_PRELOAD',
  'LOGNAME',
  'NODE_OPTIONS',
  'PATH',
  'PERL5LIB',
  'PROMPT_COMMAND',
  'PYTHONHOME',
  'PYTHONPATH',
  'RUBYLIB',
  'SHELL',
  'USER',
]);

/** Only the bash tool's executor hands staged credentials to the command it runs. */
export function supportsOneTimeCredentials(toolName: string): boolean {
  return toolName === 'bash_code_execute_tool';
}

export interface CredentialToStage {
  key: string;
  secret: string;
  ttlSeconds: number;
}

export interface StagedCredential {
  handleId: string;
  key: string;
}

interface StageResponse {
  staged: Array<{ handle_id: string; key: string }>;
}

/** The server refused a request; `detail` is its explanation when it gave one. */
export class OneTimeCredentialError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
  ) {
    super(detail ?? `HTTP ${status}`);
    this.name = 'OneTimeCredentialError';
  }
}

async function postJson(path: string, body: unknown): Promise<Response> {
  const resp = await fetch(`${API_BASE_URL}/approvals/credentials${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = ((await resp.json().catch(() => ({}))) as { detail?: unknown }).detail;
    throw new OneTimeCredentialError(resp.status, typeof detail === 'string' ? detail : undefined);
  }
  return resp;
}

export async function stageOneTimeCredentials(
  chatId: string,
  command: string,
  credentials: CredentialToStage[],
): Promise<StagedCredential[]> {
  const resp = await postJson('', {
    chat_id: chatId,
    command,
    credentials: credentials.map(({ key, secret, ttlSeconds }) => ({
      key,
      secret,
      ttl_seconds: ttlSeconds,
      single_use: true,
    })),
  });
  const { staged } = (await resp.json()) as StageResponse;
  return staged.map(({ handle_id, key }) => ({ handleId: handle_id, key }));
}

export async function wipeOneTimeCredentials(chatId: string, handleIds: string[]): Promise<void> {
  if (handleIds.length === 0) {
    return;
  }
  await postJson('/wipe', { chat_id: chatId, handle_ids: handleIds });
}
