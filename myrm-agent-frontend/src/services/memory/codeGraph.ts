/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * CodeGraph Memory Asset and Impact Analysis DTOs and API clients:
 * - scanWorkspaceCodeGraph
 * - analyzeCodeImpact
 * - queryCodeSymbols
 * - getCodeGraphAssetMetadata
 *
 * [POS]
 * Frontend API client for CodeGraph topology indexing and pre-modification blast radius assessment.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type CodeSymbolKind = 'FUNCTION' | 'CLASS' | 'METHOD' | 'VARIABLE' | string;
export type ImpactRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;

export interface CodeSymbolItem {
  symbol_id: string;
  name: string;
  kind: CodeSymbolKind;
  file_path: string;
  line_start: number;
  line_end: number;
  parameters: string[];
  return_type: string;
  docstring: string;
}

export interface ScanWorkspaceRequest {
  workspace_dir: string;
  incremental?: boolean;
  max_files?: number;
}

export interface ScanWorkspaceResponse {
  scanned_files_count: number;
  indexed_symbols_count: number;
  total_symbols: number;
  repo_id: string;
  version_hash: string;
}

export interface AnalyzeImpactRequest {
  symbol_name: string;
  file_path?: string;
  max_depth?: number;
}

export interface AnalyzeImpactResponse {
  target_symbol_id: string;
  target_symbol_name: string;
  file_path: string;
  blast_radius: number;
  risk_level: ImpactRiskLevel;
  direct_callers: string[];
  indirect_callers: string[];
  affected_files: string[];
  safety_recommendations: string[];
}

export interface QuerySymbolsParams {
  query?: string;
  kind?: string;
  limit?: number;
}

export interface SymbolListResponse {
  total: number;
  symbols: CodeSymbolItem[];
}

export interface CodeGraphAssetResponse {
  repo_id: string;
  version_hash: string;
  total_symbols: number;
  total_edges: number;
  updated_at: number;
}

export const scanWorkspaceCodeGraph = async (
  request: ScanWorkspaceRequest,
): Promise<ScanWorkspaceResponse> => {
  return apiRequest<ScanWorkspaceResponse>('/memory/codegraph/scan', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const analyzeCodeImpact = async (
  request: AnalyzeImpactRequest,
): Promise<AnalyzeImpactResponse> => {
  return apiRequest<AnalyzeImpactResponse>('/memory/codegraph/impact', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const queryCodeSymbols = async (
  params?: QuerySymbolsParams,
): Promise<SymbolListResponse> => {
  const searchParams = new URLSearchParams();
  if (params?.query) {
    searchParams.set('query', params.query);
  }
  if (params?.kind) {
    searchParams.set('kind', params.kind);
  }
  if (params?.limit) {
    searchParams.set('limit', String(params.limit));
  }
  const queryString = searchParams.toString();
  const endpoint = queryString
    ? `/memory/codegraph/symbols?${queryString}`
    : '/memory/codegraph/symbols';

  return apiRequest<SymbolListResponse>(endpoint);
};

export const getCodeGraphAssetMetadata = async (): Promise<CodeGraphAssetResponse> => {
  return apiRequest<CodeGraphAssetResponse>('/memory/codegraph/asset');
};
