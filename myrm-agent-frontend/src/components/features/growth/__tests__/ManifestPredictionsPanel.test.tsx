/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ManifestPredictionsPanel from '../ManifestPredictionsPanel';
import * as skillService from '@/services/skill';

const translationMap: Record<string, string> = {
  title: 'Change Manifest & Prediction Attribution',
  description: 'Records falsifiable metric hypotheses before evolution.',
  manifestId: 'Manifest ID',
  targetComponent: 'Target Component',
  rationale: 'Rationale',
  verdict: 'Verdict',
  recommendedAction: 'Recommended Action',
  confidence: 'Confidence',
  metricsTitle: 'Falsifiable Metric Predictions vs Reality',
  metricName: 'Metric',
  baseline: 'Baseline',
  predictedTarget: 'Predicted Target',
  actualValue: 'Actual Value',
  delta: 'Delta',
  explanation: 'Explanation',
  rollbackPatch: 'Rollback Patch',
  viewRollbackPatch: 'View Rollback Patch',
  hideRollbackPatch: 'Hide Rollback Patch',
  evaluateNow: 'Verify Attribution Now',
  evaluating: 'Verifying...',
  'actions.keep': 'Keep Changes',
  'actions.rollback': 'Rollback Suggested',
  'actions.re_evaluate': 'Re-evaluate',
  'verdicts.confirmed': 'Confirmed',
  'verdicts.refuted': 'Refuted',
  'verdicts.regression': 'Regression',
  'verdicts.inconclusive': 'Inconclusive',
};
const stableT = (key: string) => translationMap[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ManifestPredictionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders change manifest details and metric predictions correctly', async () => {
    vi.spyOn(skillService, 'evaluateManifestAttribution').mockResolvedValueOnce({
      manifest_id: 'test-manifest-001',
      overall_verdict: 'confirmed',
      metric_attributions: [
        {
          metric_name: 'pass_rate',
          predicted_target: 0.9,
          actual_value: 0.95,
          delta: 0.35,
          verdict: 'confirmed',
          explanation: 'Target exceeded',
        },
      ],
      confidence_score: 0.95,
      recommended_action: 'keep',
    });

    render(
      <ManifestPredictionsPanel
        initialManifest={{
          manifest_id: 'test-manifest-001',
          target_component: 'skills/web_search',
          rationale: 'Fix search extraction',
          predictions: [
            {
              metric_name: 'pass_rate',
              direction: 'increase',
              baseline_value: 0.6,
              target_value: 0.9,
              tolerance: 0.05,
            },
          ],
          actual_metrics: {
            pass_rate: 0.95,
          },
          rollback_patch: 'diff --git a/test b/test',
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('test-manifest-001')).toBeInTheDocument();
      expect(screen.getByText('skills/web_search')).toBeInTheDocument();
      expect(screen.getByText('Keep Changes')).toBeInTheDocument();
      expect(screen.getByText('pass_rate')).toBeInTheDocument();
    });
  });

  it('handles regression verdict and displays rollback recommended action', async () => {
    vi.spyOn(skillService, 'evaluateManifestAttribution').mockResolvedValueOnce({
      manifest_id: 'test-manifest-reg',
      overall_verdict: 'regression',
      metric_attributions: [
        {
          metric_name: 'pass_rate',
          predicted_target: 0.9,
          actual_value: 0.4,
          delta: -0.2,
          verdict: 'regression',
          explanation: 'Severe regression below baseline',
        },
      ],
      confidence_score: 0.95,
      recommended_action: 'rollback',
    });

    render(
      <ManifestPredictionsPanel
        initialManifest={{
          manifest_id: 'test-manifest-reg',
          target_component: 'harness/eval',
          rationale: 'Test regression detection',
          predictions: [
            {
              metric_name: 'pass_rate',
              direction: 'increase',
              baseline_value: 0.6,
              target_value: 0.9,
              tolerance: 0.05,
            },
          ],
          actual_metrics: {
            pass_rate: 0.4,
          },
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText('Rollback Suggested').length).toBeGreaterThanOrEqual(1);
    });
  });
});
