import { apiRequest } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExportFormatInfo {
  id: string;
  name: string;
  description: string;
}

export interface ExportRequest {
  formats: string[];
  redact_pii: boolean;
  max_samples: number;
  require_success: boolean;
  min_turns: number;
  min_content_length: number;
  start_time?: number | null;
  end_time?: number | null;
  incremental: boolean;
}

export interface ExportReport {
  total_sessions_scanned: number;
  traces_passed_quality: number;
  traces_deduplicated: number;
  samples_exported: number;
  pii_redactions: number;
  output_files: string[];
  duration_ms: number;
  errors: string[];
}

export interface ExportFileInfo {
  name: string;
  format: string;
  size_bytes: number;
  line_count: number;
  modified_at: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function listExportFormats(): Promise<ExportFormatInfo[]> {
  const res = await apiRequest<{ formats: ExportFormatInfo[] }>('/datasets/formats');
  return res.formats;
}

export async function triggerExport(request: ExportRequest): Promise<ExportReport> {
  return apiRequest<ExportReport>('/datasets/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

export async function listExportFiles(): Promise<ExportFileInfo[]> {
  const res = await apiRequest<{ files: ExportFileInfo[] }>('/datasets/files');
  return res.files;
}

export function getExportFileDownloadUrl(filename: string): string {
  return `/datasets/files/${encodeURIComponent(filename)}`;
}
