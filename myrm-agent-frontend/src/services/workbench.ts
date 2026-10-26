/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - TerminalExecRequest, TerminalExecResponse
 * - TERMINAL_TIMEOUT_SECONDS, executeTerminalCommand
 *
 * [POS]
 * Client service layer for the auxiliary workbench terminal. The call names the chat whose workspace it runs in.
 * The request is silent: the terminal panel explains a failure itself, in the user's language, instead of the
 * global toast repeating the server's raw message.
 * File browsing is not here: the Files tab uses the workspace browser's own services.
 */

import { apiClient } from './api';

export interface TerminalExecRequest {
  chat_id: string;
  command: string;
  cwd?: string | null;
  timeout_seconds?: number;
}

export interface TerminalExecResponse {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  truncated: boolean;
}

/** How long the server lets one command run before it stops it. */
export const TERMINAL_TIMEOUT_SECONDS = 30;

export async function executeTerminalCommand(
  chatId: string,
  command: string,
  cwd?: string,
  timeoutSeconds = TERMINAL_TIMEOUT_SECONDS,
): Promise<TerminalExecResponse> {
  const payload: TerminalExecRequest = {
    chat_id: chatId,
    command,
    cwd: cwd ?? null,
    timeout_seconds: timeoutSeconds,
  };
  return apiClient.post<TerminalExecResponse>('/workbench/terminal/exec', payload, { silent: true });
}
