/**
 * 专家导出 API 服务（Agent Plugins 1.0.0 ZIP）
 *
 * [INPUT]
 * @/lib/api::apiRequest,fetchWithTimeout,ApiError (POS: frontend API request helper)
 * @/services/skill::RedactionResponse (POS: 脱敏发现的差异结构，与技能导出同形)
 *
 * [OUTPUT]
 * previewExpertExport / downloadExpertPackage、ExpertExportError、expertExportErrorCode（拒绝码识别）与导出契约 DTO。
 *
 * [POS]
 * Frontend 专家导出 API client。`/plugins/export/*` REST 契约；脱敏决定语义与技能导出一致。
 */

import { ApiError, apiRequest, fetchWithTimeout } from '@/lib/api';
import type { RedactionResponse } from '@/services/skill';

const EXPORT_API_PREFIX = '/plugins/export';

/** 专家在预览之后被改动：保留/忽略脱敏的索引已失效，需重新预览 */
export const EXPERT_EXPORT_CHANGED_SINCE_PREVIEW = 'export_changed_since_preview';

/** 后端以稳定 `error_code` 报告的拒绝原因；界面按码本地化，不展示后端英文原文 */
const EXPORT_ERROR_CODES = [
  'expert_not_found',
  'built_in_expert',
  EXPERT_EXPORT_CHANGED_SINCE_PREVIEW,
  'redaction_review_required',
  'package_rejected',
] as const;

export type ExpertExportErrorCode = (typeof EXPORT_ERROR_CODES)[number];

export interface ExpertExportCard {
  name: string;
  description: string;
  is_entry: boolean;
  skill_names: string[];
  connector_names: string[];
  subagent_names: string[];
  tool_names: string[];
  /** 作者所用模型，仅向接收方展示，不会被应用 */
  recommended_model: string | null;
}

export interface ExpertExportSkillCard {
  name: string;
  /** custom：文件随包携带；preset：仅按名引用 */
  source: 'custom' | 'preset';
  file_count: number;
  version: string | null;
  origin: string | null;
}

export interface ExpertExportConnectorCard {
  name: string;
  type: string;
  /** 接收方需要自行提供的密钥名（值绝不随包） */
  secret_keys: string[];
}

export interface ExpertExportWorkspaceFile {
  path: string;
  size: number;
}

export type ExpertExportOmittedKind = 'skill' | 'skill_file' | 'connector' | 'expert' | 'workspace_file' | 'setting';

export interface ExpertExportOmittedItem {
  kind: ExpertExportOmittedKind;
  name: string;
  /** 后端原因码，由界面本地化 */
  reason: string;
  owner: string | null;
}

export interface ExpertExportPreview {
  plugin_name: string;
  version: string;
  experts: ExpertExportCard[];
  skills: ExpertExportSkillCard[];
  connectors: ExpertExportConnectorCard[];
  workspace_files: ExpertExportWorkspaceFile[];
  omitted: ExpertExportOmittedItem[];
  redactions: Record<string, RedactionResponse[]> | null;
  is_safe: boolean;
  /** 预览所基于的内容摘要；导出携带“保留”决定时必须回传 */
  review_digest: string;
  package_bytes: number | null;
  /** 试构建失败原因（正式导出同样会失败） */
  build_error: string | null;
}

export interface ExpertExportRequest {
  agentId: string;
  applyRedactions: boolean;
  /** 文件路径 -> 作者选择原样保留的发现索引 */
  ignoredRedactions: Record<string, number[]>;
  reviewDigest?: string;
}

/** 专家导出被拒绝（携带后端机器可读错误码） */
export class ExpertExportError extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message);
    this.name = 'ExpertExportError';
  }
}

/** 导出请求失败时后端给出的已知拒绝码；未携带或不认识时为 null */
export function expertExportErrorCode(error: unknown): ExpertExportErrorCode | null {
  const code =
    error instanceof ExpertExportError ? error.code : error instanceof ApiError ? error.data?.error_code : undefined;
  return EXPORT_ERROR_CODES.find((known) => known === code) ?? null;
}

export async function previewExpertExport(agentId: string): Promise<ExpertExportPreview> {
  return apiRequest<ExpertExportPreview>(`${EXPORT_API_PREFIX}/preview`, {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId }),
    // The dialog reports the failure itself; a second global toast would duplicate it.
    silent: true,
    // Scanning and a dry-run build are CPU-bound on large skills.
    timeout: 120_000,
  });
}

/** 后端 detail 为字符串或 {message, error_code} */
async function toExpertExportError(response: Response): Promise<ExpertExportError> {
  const raw = await response.text();
  try {
    const detail: unknown = (JSON.parse(raw) as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return new ExpertExportError(detail);
    }
    if (detail && typeof detail === 'object') {
      const { message, error_code: code } = detail as { message?: string; error_code?: string };
      return new ExpertExportError(message ?? raw, code);
    }
  } catch {
    // 非 JSON 响应：回退为原始文本
  }
  return new ExpertExportError(raw);
}

/** 下载专家包；返回 blob 与后端 Content-Disposition 提供的文件名 */
export async function downloadExpertPackage(
  request: ExpertExportRequest,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetchWithTimeout(
    EXPORT_API_PREFIX,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
      },
      body: JSON.stringify({
        agent_id: request.agentId,
        apply_redactions: request.applyRedactions,
        ignored_redactions: request.ignoredRedactions,
        review_digest: request.reviewDigest,
      }),
    },
    120_000,
  );

  if (!response.ok) {
    throw await toExpertExportError(response);
  }

  const disposition = response.headers.get('Content-Disposition') || '';
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/);
  return { blob: await response.blob(), filename: filenameMatch ? filenameMatch[1] : null };
}
