/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - SourceLocation: Component file location and confidence
 * - InspectedElementContext: Comprehensive element snapshot with Fiber source
 * - SelfEvolutionLocateRequest / SelfEvolutionLocateResponse: Remote AST search models
 * - SelfEvolutionTaskCreateRequest / SelfEvolutionTaskResponse: Task creation models
 * - SelfEvolutionRecoverRequest / SelfEvolutionRecoverResponse: Rollback models
 * - locateSourceCandidates: Query backend for component source matching
 * - createSelfEvolutionTask: Submit inspector feedback and launch task
 * - listSelfEvolutionTasks: Retrieve task history
 * - recoverSelfEvolution: Rollback to safe checkpoint
 *
 * [POS]
 * Client service layer for Designer's Eye UI Element Inspector and Self-Evolution Pipeline.
 * Single file < 160 lines. Zero `any` types.
 */

import { apiClient } from './api';

export interface SourceLocation {
  fileName: string;
  lineNumber?: number;
  columnNumber?: number;
  componentName?: string;
  confidence: 'fiber_debug' | 'data_attribute' | 'hierarchy_match' | 'tag_fallback';
}

export interface InspectedElementContext {
  domSelector: string;
  tagName: string;
  classes: string[];
  componentHint?: string;
  componentHierarchy?: string[];
  primarySource?: SourceLocation;
  candidates?: SourceLocation[];
  textSnippet?: string;
  computedStyleSummary?: Record<string, string>;
}

export interface SelfEvolutionLocateRequest {
  dom_selector: string;
  tag_name: string;
  classes: string[];
  component_hint?: string;
  component_hierarchy?: string[];
  text_snippet?: string;
}

export interface SelfEvolutionLocateResponse {
  candidates: SourceLocation[];
  matched_file?: string;
  confidence: string;
}

export interface SelfEvolutionTaskCreateRequest {
  dom_selector: string;
  tag_name: string;
  classes: string[];
  component_hint?: string;
  component_hierarchy?: string[];
  primary_source?: SourceLocation;
  candidates?: SourceLocation[];
  text_snippet?: string;
  user_prompt: string;
  preset_tags: string[];
  computed_style_summary?: Record<string, string>;
}

export interface SelfEvolutionTaskResponse {
  task_id: string;
  status: 'pending' | 'verified' | 'failed' | 'rolled_back';
  dom_selector: string;
  tag_name: string;
  component_hint?: string;
  user_prompt: string;
  target_component_file?: string;
  target_line_number?: number;
  diff_summary?: string;
  recoverable_checkpoint_id: string;
  created_at: string;
}

export interface SelfEvolutionRecoverRequest {
  checkpoint_id?: string;
  task_id?: string;
}

export interface SelfEvolutionRecoverResponse {
  success: boolean;
  message: string;
  restored_checkpoint_id: string;
}

const SELF_EVOLUTION_BASE = '/api/v1/self-evolution';

export async function locateSourceCandidates(
  payload: SelfEvolutionLocateRequest,
): Promise<SelfEvolutionLocateResponse> {
  return apiClient.post<SelfEvolutionLocateResponse>(`${SELF_EVOLUTION_BASE}/locate`, payload);
}

export async function createSelfEvolutionTask(
  payload: SelfEvolutionTaskCreateRequest,
): Promise<SelfEvolutionTaskResponse> {
  return apiClient.post<SelfEvolutionTaskResponse>(`${SELF_EVOLUTION_BASE}/tasks`, payload);
}

export async function listSelfEvolutionTasks(): Promise<SelfEvolutionTaskResponse[]> {
  return apiClient.get<SelfEvolutionTaskResponse[]>(`${SELF_EVOLUTION_BASE}/tasks`);
}

export async function recoverSelfEvolution(
  payload: SelfEvolutionRecoverRequest,
): Promise<SelfEvolutionRecoverResponse> {
  return apiClient.post<SelfEvolutionRecoverResponse>(`${SELF_EVOLUTION_BASE}/recover`, payload);
}
