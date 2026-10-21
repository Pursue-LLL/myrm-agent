/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - WorkbenchFileNode, FileTreeResponse, FileContentResponse, DiffHunk, FileDiffResponse
 * - TerminalExecResponse, PluginItem, PluginProbeResponse
 * - fetchWorkspaceFiles, fetchFileContent, computeFileDiff, executeTerminalCommand
 * - fetchWorkbenchPlugins, probePluginHealth
 *
 * [POS]
 * Client service layer for Independent Multi-Tab Auxiliary Workbench (Item 25).
 * Single file < 170 lines. Zero `any` types.
 */

import { apiClient } from './api';

export type NodeType = 'file' | 'directory';
export type PluginStatus = 'healthy' | 'degraded' | 'error' | 'inactive';

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
  modified_at: string;
}

export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  lines: string[];
}

export interface FileDiffRequest {
  file_path: string;
  original_content?: string | null;
  modified_content?: string | null;
}

export interface FileDiffResponse {
  file_path: string;
  unified_diff: string;
  additions: number;
  deletions: number;
  hunks: DiffHunk[];
}

export interface TerminalExecRequest {
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
}

export interface PluginItem {
  plugin_id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  github_repo?: string | null;
  status: PluginStatus;
  is_installed: boolean;
  last_probed_at?: string | null;
}

export interface PluginProbeResponse {
  plugin_id: string;
  status: PluginStatus;
  latency_ms: number;
  message: string;
  details: Record<string, string>;
}

export async function fetchWorkspaceFiles(
  rootDir?: string,
  maxDepth = 3,
): Promise<FileTreeResponse> {
  const params: Record<string, string> = { max_depth: String(maxDepth) };
  if (rootDir) {
    params.root_dir = rootDir;
  }
  const queryString = new URLSearchParams(params).toString();
  return apiClient.get<FileTreeResponse>(`/workbench/files?${queryString}`);
}

export async function fetchFileContent(path: string): Promise<FileContentResponse> {
  const queryString = new URLSearchParams({ path }).toString();
  return apiClient.get<FileContentResponse>(`/workbench/file/content?${queryString}`);
}

export async function computeFileDiff(req: FileDiffRequest): Promise<FileDiffResponse> {
  return apiClient.post<FileDiffResponse>('/workbench/diff', req);
}

export async function executeTerminalCommand(
  command: string,
  cwd?: string,
  timeoutSeconds = 30,
): Promise<TerminalExecResponse> {
  const payload: TerminalExecRequest = {
    command,
    cwd: cwd ?? null,
    timeout_seconds: timeoutSeconds,
  };
  return apiClient.post<TerminalExecResponse>('/workbench/terminal/exec', payload);
}

export async function fetchWorkbenchPlugins(): Promise<PluginItem[]> {
  return apiClient.get<PluginItem[]>('/workbench/plugins');
}

export async function probePluginHealth(pluginId: string): Promise<PluginProbeResponse> {
  return apiClient.post<PluginProbeResponse>(`/workbench/plugins/${pluginId}/probe`, {});
}
