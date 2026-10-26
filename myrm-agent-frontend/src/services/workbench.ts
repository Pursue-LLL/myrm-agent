/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - TerminalExecRequest, TerminalExecResponse
 * - executeTerminalCommand
 *
 * [POS]
 * Client service layer for the auxiliary workbench terminal. The call names the chat whose workspace it runs in.
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

export async function executeTerminalCommand(
  chatId: string,
  command: string,
  cwd?: string,
  timeoutSeconds = 30,
): Promise<TerminalExecResponse> {
  const payload: TerminalExecRequest = {
    chat_id: chatId,
    command,
    cwd: cwd ?? null,
    timeout_seconds: timeoutSeconds,
  };
  return apiClient.post<TerminalExecResponse>('/workbench/terminal/exec', payload);
}
