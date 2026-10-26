/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - WorkbenchFileNode, FileTreeResponse, FileContentResponse
 * - TerminalExecRequest, TerminalExecResponse
 * - fetchWorkspaceFiles, fetchFileContent, executeTerminalCommand
 *
 * [POS]
 * Client service layer for the auxiliary workbench. Every call names the chat whose workspace it works in.
 */

import { apiClient } from './api';

export type NodeType = 'file' | 'directory';

export interface WorkbenchFileNode {
  name: string;
  path: string;
  node_type: NodeType;
  size_bytes: number;
  modified_at: string;
  extension: string;
  children?: WorkbenchFileNode[] | null;
}

export interface FileTreeResponse {
  root_path: string;
  nodes: WorkbenchFileNode[];
  total_files: number;
  total_dirs: number;
}

export interface FileContentResponse {
  path: string;
  content: string;
  language: string;
  size_bytes: number;
  is_binary: boolean;
  truncated: boolean;
  modified_at: string;
}

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

export async function fetchWorkspaceFiles(
  chatId: string,
  rootDir?: string,
  maxDepth = 3,
): Promise<FileTreeResponse> {
  const params: Record<string, string> = { chat_id: chatId, max_depth: String(maxDepth) };
  if (rootDir) {
    params.root_dir = rootDir;
  }
  const queryString = new URLSearchParams(params).toString();
  return apiClient.get<FileTreeResponse>(`/workbench/files?${queryString}`);
}

export async function fetchFileContent(chatId: string, path: string): Promise<FileContentResponse> {
  const queryString = new URLSearchParams({ chat_id: chatId, path }).toString();
  return apiClient.get<FileContentResponse>(`/workbench/file/content?${queryString}`);
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
