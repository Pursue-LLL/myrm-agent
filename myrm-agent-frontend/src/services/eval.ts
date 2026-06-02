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

export const evalService = {
  /**
   * Get the current evaluation cases
   */
  async getEvalCases(): Promise<EvalCasesResponse> {
    return apiRequest('/eval/cases');
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
  async runEvaluation(): Promise<{ status: string }> {
    return apiRequest('/eval/run', {
      method: 'POST',
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
};
