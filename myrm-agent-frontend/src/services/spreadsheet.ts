/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 * @/lib/api::API_BASE_URL (POS: backend base for raw blob fetch)
 *
 * [OUTPUT]
 * - SpreadsheetTheme, ColumnType, SpreadsheetColumn, SpreadsheetRow
 * - SpreadsheetGenerateRequest, OfficePlatform, OfficeSyncRequest, OfficeSyncResponse
 * - generateStyledExcelBlob: Requests and returns binary Excel Blob from backend
 * - downloadSpreadsheetAsExcel: Helper to trigger client-side file download
 * - syncSpreadsheetToOffice: Syncs structured data to Feishu Bitable / WeCom / DingTalk
 *
 * [POS]
 * Client service layer for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline (Item 19).
 * Single file < 120 lines. Zero `any` types.
 */

import { API_BASE_URL } from '@/lib/api';
import { apiClient } from './api';

export type SpreadsheetTheme =
  | 'business_navy'
  | 'dark_gold'
  | 'financial_emerald'
  | 'tech_slate';

export type ColumnType = 'string' | 'number' | 'currency' | 'percentage' | 'date';

export interface SpreadsheetColumn {
  key: string;
  label: string;
  col_type?: ColumnType;
  width?: number | null;
}

export interface SpreadsheetRow {
  cells: Record<string, string | number | boolean | null>;
}

export interface SpreadsheetGenerateRequest {
  title: string;
  theme?: SpreadsheetTheme;
  columns: SpreadsheetColumn[];
  rows: SpreadsheetRow[];
  sheet_name?: string;
}

export type OfficePlatform = 'feishu_bitable' | 'wecom_doc' | 'dingtalk_table';

export interface OfficeSyncRequest {
  platform: OfficePlatform;
  table_name: string;
  columns: SpreadsheetColumn[];
  rows: SpreadsheetRow[];
}

export interface OfficeSyncResponse {
  platform: OfficePlatform;
  success: boolean;
  sync_id: string;
  url: string;
  record_count: number;
  message: string;
}

const SPREADSHEET_BASE = '/spreadsheet';

export async function generateStyledExcelBlob(
  payload: SpreadsheetGenerateRequest,
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${SPREADSHEET_BASE}/generate-excel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to generate excel: ${response.status} ${response.statusText}`);
  }

  return response.blob();
}

export async function downloadSpreadsheetAsExcel(
  payload: SpreadsheetGenerateRequest,
  filename?: string,
): Promise<void> {
  const blob = await generateStyledExcelBlob(payload);
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = filename || `${payload.title.replace(/\s+/g, '_')}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(downloadUrl);
}

export async function syncSpreadsheetToOffice(
  payload: OfficeSyncRequest,
): Promise<OfficeSyncResponse> {
  return apiClient.post<OfficeSyncResponse>(`${SPREADSHEET_BASE}/sync-office`, payload);
}
