import { apiRequest } from '@/lib/api';

export interface EvalSummary {
  total_cases: number;
  pass_count: number;
  fail_count: number;
  error_count: number;
  skip_count: number;
  pass_rate: number;
  all_passed: boolean;
  total_ms: number;
  report_path?: string;
}

export interface EvalRunResponse {
  status: string;
  summary: EvalSummary;
}

export interface EvalReportResponse {
  status: string;
  summary: EvalSummary | null;
}

export interface EvalStatusResponse {
  is_running: boolean;
  total: number;
  completed: number;
  error: string | null;
}

export interface EvalCasesResponse {
  status: string;
  content: string;
}

export interface SkillABArmMetrics {
  arm_name: string;
  skill_id: string | null;
  pass_count: number;
  total_cases: number;
  pass_rate: number;
  avg_tool_calls: number;
  total_tokens: number;
  avg_latency_ms: number;
}

export interface SkillABReport {
  dataset_id: string;
  baseline_skill_id: string | null;
  candidate_skill_id: string;
  no_skill_metrics: SkillABArmMetrics;
  baseline_metrics: SkillABArmMetrics;
  candidate_metrics: SkillABArmMetrics;
  success_rate_delta: number;
  token_savings_pct: number;
  step_reduction_pct: number;
  verdict: 'IMPROVED' | 'REGRESSED' | 'EQUIVALENT' | 'INCONCLUSIVE';
  created_at: string;
  agent_model?: string;
  judge_model?: string;
}

export interface SkillABStatusResponse {
  is_running: boolean;
  stage: string | null;
  current_arm: string | null;
  profile_progress: number;
  profile_total: number;
  case_completed: number;
  case_total: number;
  error: string | null;
  abort_requested: boolean;
}

export interface AntiContaminationAuditResponse {
  status: string;
  dataset_id: string;
  is_protected: boolean;
  canary_found: boolean;
  canary_guid: string;
  violations: string[];
  metadata: Record<string, unknown>;
}

export interface EmbedCanaryResponse {
  status: string;
  protected_content: string;
  canary_guid: string;
}

export interface EvalDatasetItem {
  id: string;
  name?: string;
  count?: number;
}

export interface EvalDatasetsResponse {
  status: string;
  datasets: EvalDatasetItem[];
}

export const evalService = {
  /**
   * List all evaluation datasets
   */
  async getDatasets(): Promise<EvalDatasetsResponse> {
    return apiRequest('/eval/datasets');
  },

  /**
   * Audit benchmark datasets against anti-contamination canary standards
   */
  async auditAntiContamination(datasetId?: string): Promise<AntiContaminationAuditResponse> {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : '';
    return apiRequest(`/eval/anti-contamination/audit${query}`);
  },

  /**
   * Embed standardized canary header into raw dataset content safely
   */
  async embedCanaryHeader(content: string): Promise<EmbedCanaryResponse> {
    return apiRequest('/eval/anti-contamination/embed-canary', {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  },

  /**
   * Get the current evaluation cases
   */
  async getEvalCases(): Promise<EvalCasesResponse> {
    return apiRequest('/eval/cases');
  },

  /**
   * Capture a chat session and append it to evaluation cases
   */
  async captureCaseFromChat(chatId: string, datasetId?: string): Promise<{ status: string }> {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : '';
    return apiRequest(`/eval/cases/from-chat/${encodeURIComponent(chatId)}${query}`, {
      method: 'POST',
    });
  },

  /**
   * Update the evaluation cases
   */
  async saveEvalCases(content: string): Promise<{ status: string }> {
    return apiRequest('/eval/cases', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  },

  /**
   * Start the evaluation suite for the current user
   */
  async runEvaluation(options?: {
    profileId?: string | null;
    datasetId?: string | null;
    benchmarkMode?: boolean;
  }): Promise<{ status: string }> {
    return apiRequest('/eval/run', {
      method: 'POST',
      body: JSON.stringify({
        profile_id: options?.profileId ?? null,
        dataset_id: options?.datasetId ?? null,
        benchmark_mode: options?.benchmarkMode ?? false,
      }),
    });
  },

  /**
   * Get the current status of the evaluation suite
   */
  async getEvalStatus(): Promise<EvalStatusResponse> {
    return apiRequest('/eval/status');
  },

  /**
   * Get the latest evaluation report summary
   */
  async getLatestReport(): Promise<EvalReportResponse> {
    return apiRequest('/eval/reports/latest');
  },

  /**
   * Start a three-arm Skill A/B evaluation
   */
  async runSkillAb(options: {
    benchmark_id: string;
    candidate_skill_id: string;
    baseline_skill_id?: string | null;
    limit?: number;
  }): Promise<{ status: string }> {
    return apiRequest('/eval/skill-ab/run', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  },

  /**
   * Get the current status of the Skill A/B evaluation
   */
  async getSkillAbStatus(): Promise<SkillABStatusResponse> {
    return apiRequest('/eval/skill-ab/status');
  },

  /**
   * Abort the running Skill A/B evaluation
   */
  async abortSkillAb(): Promise<{ aborted: boolean }> {
    return apiRequest('/eval/skill-ab/abort', {
      method: 'POST',
    });
  },

  /**
   * Get the latest Skill A/B evaluation report
   */
  async getLatestSkillAbReport(): Promise<SkillABReport> {
    return apiRequest('/eval/skill-ab/report/latest');
  },

  /**
   * List historical Skill A/B reports
   */
  async listSkillAbReports(): Promise<
    Array<{
      filename: string;
      dataset_id: string;
      candidate_skill_id: string;
      baseline_skill_id?: string | null;
      verdict: string;
      success_rate_delta: number;
      created_at: string;
    }>
  > {
    return apiRequest('/eval/skill-ab/reports');
  },
};
