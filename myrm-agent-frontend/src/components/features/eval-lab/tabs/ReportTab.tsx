import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Eye,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  XCircle,
} from 'lucide-react';

import { formatMib } from '../components/format';
import { type DownloadProgress, type EvalProgress, type ReportItem } from '../hooks/useCasesEval';
import ComponentAblationImpactRankingChip from '../components/ComponentAblationImpactRankingChip';

interface ReportTabProps {
  running: boolean;
  evalStage: string | null;
  progress: EvalProgress;
  downloadProgress: DownloadProgress | null;
  report: ReportItem | null;
  onViewDiff: (expected: string, actual: string) => void;
}

export default function ReportTab({
  running,
  evalStage,
  progress,
  downloadProgress,
  report,
  onViewDiff,
}: ReportTabProps) {
  const t = useTranslations('evalLab');

  if (running) {
    const downloading = evalStage === 'downloading';
    const downloaded = downloadProgress?.downloaded_bytes ?? 0;
    const totalBytes = downloadProgress?.total_bytes ?? 0;
    const width =
      downloading && totalBytes > 0
        ? (downloaded / totalBytes) * 100
        : progress.total > 0
          ? (progress.completed / progress.total) * 100
          : 0;

    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
        <p>
          {downloading
            ? `${t('wbBench.downloading')}: ${formatMib(downloaded)} / ${totalBytes > 0 ? formatMib(totalBytes) : '?'}`
            : `${t('report.evalRunning')} (${progress.completed} / ${progress.total})`}
        </p>
        <div className="w-64 h-2 bg-secondary rounded-full overflow-hidden">
          <div className="h-full bg-primary transition-all duration-300" style={{ width: `${width}%` }} />
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
        <AlertCircle className="w-12 h-12 opacity-20" />
        <p>{t('report.noReport')}</p>
      </div>
    );
  }

  const successRate =
    typeof report.total === 'number' && report.total > 0 ? Math.round(((report.passed ?? 0) / report.total) * 100) : 0;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="grid grid-cols-4 gap-4">
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('report.totalCases')}</span>
          <span className="text-3xl font-bold mt-1">{report.total}</span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('report.passRate')}</span>
          <span className={`text-3xl font-bold mt-1 ${successRate >= 80 ? 'text-green-500' : 'text-amber-500'}`}>
            {successRate}%
          </span>
          {report.variance_metrics && report.variance_metrics.n_attempts > 1 && (
            <span className="text-xs text-muted-foreground mt-0.5 font-mono">
              ±{(report.variance_metrics.std_dev * 100).toFixed(1)}% (Pass@{report.variance_metrics.n_attempts}:{' '}
              {Math.round(report.variance_metrics.pass_at_k * 100)}%)
            </span>
          )}
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('report.avgTime')}</span>
          <span className="text-3xl font-bold mt-1">
            {report.avg_time_secs ? report.avg_time_secs.toFixed(2) : '-'}s
          </span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('report.avgToken')}</span>
          <span className="text-3xl font-bold mt-1">{Math.round(report.avg_total_tokens || 0)}</span>
        </div>
      </div>

      {report.ablation_recommendations && report.ablation_recommendations.length > 0 && (
        <ComponentAblationImpactRankingChip
          recommendations={report.ablation_recommendations}
          profileId={report.manifest?.profile_id}
        />
      )}

      {report.manifest && (
        <div className="border rounded-lg p-4 bg-muted/10">
          <h3 className="text-sm font-medium text-muted-foreground mb-3">{t('report.environment')}</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">{t('report.envModel')}</span>
              <p className="font-mono text-xs mt-0.5">
                {report.manifest.model_provider}/{report.manifest.model_id}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envThinking')}</span>
              <p className="font-mono text-xs mt-0.5">{report.manifest.thinking_effort}</p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envVersion')}</span>
              <p className="font-mono text-xs mt-0.5">{report.manifest.harness_version}</p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envTools')}</span>
              <p className="font-mono text-xs mt-0.5 truncate" title={report.manifest.tool_policy?.join(', ')}>
                {report.manifest.tool_policy?.join(', ') || '-'}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envDataset')}</span>
              <p className="font-mono text-xs mt-0.5">{report.manifest.task_set_id}</p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envPrompt')}</span>
              <p className="font-mono text-xs mt-0.5" title={report.manifest.prompt_fingerprint}>
                {report.manifest.prompt_fingerprint?.slice(0, 12)}...
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envProfile')}</span>
              <p className="font-mono text-xs mt-0.5">{report.manifest.profile_id || '-'}</p>
            </div>
            <div>
              <span className="text-muted-foreground">{t('report.envBenchmark')}</span>
              <p className="font-mono text-xs mt-0.5">{report.manifest.benchmark_mode ? 'ON' : 'OFF'}</p>
            </div>
            {report.manifest.judge_model && report.manifest.judge_model !== 'none' && (
              <div>
                <span className="text-muted-foreground">{t('report.envJudge')}</span>
                <p className="font-mono text-xs mt-0.5">{report.manifest.judge_model}</p>
              </div>
            )}
            {report.manifest.benchmark_mode && (
              <div>
                <span className="text-muted-foreground">{t('report.envBudget')}</span>
                <p className="font-mono text-xs mt-0.5">
                  {report.manifest.max_tool_calls != null
                    ? `${report.manifest.max_tool_calls} ${t('report.budgetToolCalls')}`
                    : '-'}
                  {' / '}
                  {report.manifest.max_iterations != null
                    ? `${report.manifest.max_iterations} ${t('report.budgetIterations')}`
                    : '-'}
                </p>
              </div>
            )}
            {typeof report.decontam_active === 'boolean' && (
              <div>
                <span className="text-muted-foreground">{t('report.envDecontam')}</span>
                <p className="text-xs mt-0.5">
                  <span
                    className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                      report.decontam_active
                        ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {report.decontam_active ? t('report.decontamOn') : t('report.decontamOff')}
                  </span>
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 9-Class Trajectory Failure Mode Analysis & Pareto Chart */}
      {report.failure_analysis && report.failure_analysis.total_failures > 0 && (
        <div className="border rounded-lg p-4 bg-muted/10 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-500" />
              {t('report.failureAnalysisTitle')}
            </h3>
            <span className="text-xs text-muted-foreground">
              {t('report.totalFailuresCount', { count: report.failure_analysis.total_failures })}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
            {Object.entries(report.failure_analysis.pareto_percentages).map(([mode, pct]) => {
              const count = report.failure_analysis?.failure_distribution[mode] ?? 0;
              return (
                <div key={mode} className="p-2.5 rounded border bg-card flex flex-col justify-between gap-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground truncate" title={mode}>
                      {t(`report.failureModes.${mode}`) || mode}
                    </span>
                    <span className="font-bold text-amber-600 dark:text-amber-400">{pct}%</span>
                  </div>
                  <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
                    <div className="bg-amber-500 h-full rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-[10px] text-muted-foreground">{count} cases</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Component Ablation Leverage & Harness Edit Ranking Chips */}
      {report.ablation_recommendations && report.ablation_recommendations.length > 0 && (
        <div className="border rounded-lg p-4 bg-muted/10 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              {t('report.ablationTitle')}
            </h3>
            <span className="text-xs text-muted-foreground">
              {t('report.ablationSubtitle')}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {report.ablation_recommendations.map((rec, idx) => {
              const tierBadgeClass =
                rec.component === 'tool'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                  : rec.component === 'middleware'
                  ? 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20'
                  : rec.component === 'memory'
                  ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';

              return (
                <div
                  key={idx}
                  className="p-3.5 rounded-lg border bg-card flex flex-col justify-between gap-2.5 transition-all hover:border-primary/40 shadow-2xs"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase border ${tierBadgeClass}`}>
                          {t(`report.ablationTiers.${rec.component}`) || rec.component}
                        </span>
                        <span className="text-xs font-semibold text-foreground">
                          {rec.title}
                        </span>
                      </div>
                      <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
                        {rec.affected_case_count} cases
                      </span>
                    </div>

                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {rec.reason}
                    </p>
                  </div>

                  <div className="pt-2 border-t flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1 font-mono">
                      <Sliders className="w-3 h-3 text-primary/70" />
                      {rec.target_config_tab} → {rec.target_setting_key}
                    </span>
                    <span className="text-[10px] font-medium text-primary">
                      {t('report.ablationRoiOrder', { priority: rec.priority })}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Fleet Difficulty Shard Breakdown */}
      {report.variance_metrics?.difficulty_breakdown &&
        Object.keys(report.variance_metrics.difficulty_breakdown).length > 0 && (
          <div className="border rounded-lg p-4 bg-muted/10 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Layers className="w-4 h-4 text-primary" />
                {t('report.difficultyShardTitle')}
              </h3>
              <span className="text-xs text-muted-foreground">
                {t('report.fleetAttempts', { count: report.variance_metrics.n_attempts })}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {Object.entries(report.variance_metrics.difficulty_breakdown).map(([tier, stats]) => (
                <div key={tier} className="p-3 rounded border bg-card flex flex-col justify-between gap-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold uppercase tracking-wider text-muted-foreground">{tier}</span>
                    <span className="font-bold text-foreground">{(stats.pass_rate * 100).toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
                    <div className="bg-primary h-full rounded-full" style={{ width: `${stats.pass_rate * 100}%` }} />
                  </div>
                  <span className="text-[10px] text-muted-foreground">{stats.total_runs} runs</span>
                </div>
              ))}
            </div>
          </div>
        )}

      <div className="space-y-3">
        <h3 className="text-lg font-medium">{t('report.executionDetails')}</h3>
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-muted/50 border-b">
              <tr>
                <th className="px-4 py-3 font-medium">{t('report.status')}</th>
                <th className="px-4 py-3 font-medium">{t('report.messageSnippet')}</th>
                <th className="px-4 py-3 font-medium">{t('report.tokenUsage')}</th>
                <th className="px-4 py-3 font-medium">{t('report.duration')}</th>
                <th className="px-4 py-3 font-medium">{t('report.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {report.cases?.map((c, i) => (
                <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    {c.passed === true ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle2 className="w-4 h-4" />
                        {t('report.passed')}
                      </span>
                    ) : c.passed === false ? (
                      <span className="flex items-center gap-1 text-red-600">
                        <XCircle className="w-4 h-4" />
                        {t('report.failed')}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <Clock className="w-4 h-4" />
                        {t('report.pending')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <span className="block truncate" title={c.case?.message}>
                      {c.case?.message || t('report.multiTurn')}
                    </span>
                    {(() => {
                      const scores = c.scores as
                        | {
                            pass_rate?: number;
                            tests_passed?: number;
                            tests_total?: number;
                            span_recall?: number;
                            distinct_sources?: number;
                          }
                        | undefined;
                      return (
                        <>
                          {scores?.pass_rate != null && (
                            <span
                              className={`ml-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                                scores.pass_rate >= 1
                                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                              }`}
                            >
                              {scores.pass_rate >= 1 ? '100%' : `${Math.min(99, Math.floor(scores.pass_rate * 100))}%`}
                              {scores.tests_total != null && ` · ${scores.tests_passed ?? 0}/${scores.tests_total}`}
                            </span>
                          )}
                          {scores?.span_recall != null && (
                            <span
                              className={`ml-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                                scores.span_recall >= 1
                                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                              }`}
                              title={t('report.retrievalSpanRecallTitle') || 'Retrieval Span Recall'}
                            >
                              {`Span ${Math.round(scores.span_recall * 100)}%`}
                              {scores.distinct_sources != null && ` · ${scores.distinct_sources} sources`}
                            </span>
                          )}
                        </>
                      );
                    })()}
                    {(c.limit_reached ||
                      (c.blocked_count ?? 0) > 0 ||
                      (c.tool_call_details?.length ?? 0) > 0 ||
                      c.canary_verified !== undefined ||
                      c.contamination_audit?.cheat_detected) && (
                      <span className="flex items-center gap-1 mt-1 flex-wrap">
                        {c.canary_verified === true && (
                          <span
                            className="inline-flex items-center gap-0.5 px-1 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[10px] font-semibold"
                            title={t('report.canaryVerified')}
                          >
                            <ShieldCheck className="w-2.5 h-2.5" />
                            Canary
                          </span>
                        )}
                        {c.canary_verified === false && (
                          <span
                            className="inline-flex items-center gap-0.5 px-1 rounded bg-red-500/15 text-red-600 dark:text-red-400 text-[10px] font-semibold"
                            title={t('report.canaryLeak')}
                          >
                            <ShieldAlert className="w-2.5 h-2.5" />
                            Canary Leak
                          </span>
                        )}
                        {c.contamination_audit?.cheat_detected && (
                          <span
                            className="inline-flex items-center gap-0.5 px-1 rounded bg-red-500/15 text-red-600 dark:text-red-400 text-[10px] font-semibold"
                            title={t('report.contaminationViolationTitle')}
                          >
                            <ShieldAlert className="w-2.5 h-2.5" />
                            {t('report.contaminationViolation')}
                          </span>
                        )}
                        {c.limit_reached && (
                          <span
                            className="px-1 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 text-[10px] font-semibold"
                            title={`${t('report.limitHitTitle')} · ${c.limit_reached}`}
                          >
                            {t('report.limitHit')}
                          </span>
                        )}
                        {(c.blocked_count ?? 0) > 0 && (
                          <span
                            className="px-1 rounded bg-violet-500/15 text-violet-600 dark:text-violet-400 text-[10px] font-semibold"
                            title={t('report.blockedTitle')}
                          >
                            {t('report.blocked')} {c.blocked_count}
                          </span>
                        )}
                        {(c.tool_call_details?.length ?? 0) > 0 && (
                          <span
                            className="text-[10px] text-muted-foreground font-mono"
                            title={t('report.toolCallsTitle')}
                          >
                            {c.tool_call_details?.length}×
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">{c.usage?.total_tokens || 0}</td>
                  <td className="px-4 py-3">{c.time_secs ? c.time_secs.toFixed(2) : '-'}s</td>
                  <td className="px-4 py-3">
                    {c.contamination_audit?.violations && c.contamination_audit.violations.length > 0 && (
                      <div className="mb-1.5 p-1.5 rounded bg-red-500/10 border border-red-500/20 text-xs text-red-600 dark:text-red-400">
                        <div className="flex items-center gap-1 font-semibold text-[11px]">
                          <ShieldAlert className="w-3 h-3" />
                          <span>{t('report.contaminationViolation')}:</span>
                        </div>
                        {c.contamination_audit.violations.map((v, vIdx) => (
                          <div key={vIdx} className="text-[10px] mt-0.5 truncate max-w-[300px]" title={v.details}>
                            {v.tool_name ? `[${v.tool_name}] ` : ''}
                            {v.details}
                          </div>
                        ))}
                      </div>
                    )}
                    {c.details ? (
                      <div className="flex flex-col items-start gap-1">
                        <p className="max-w-[320px] truncate text-xs text-muted-foreground" title={String(c.details)}>
                          {String(c.details)}
                        </p>
                        <button
                          onClick={() => {
                            const expected = {
                              tools: c.case?.expected_tools || [],
                              output: c.case?.state_assertions?.length ? c.case.state_assertions : undefined,
                            };
                            const actual = {
                              tools: c.actual_tools || [],
                              output: c.actual_output || '',
                            };
                            onViewDiff(JSON.stringify(expected, null, 2), JSON.stringify(actual, null, 2));
                          }}
                          className="flex items-center gap-1 text-primary hover:underline"
                        >
                          <Eye className="w-4 h-4" /> {t('report.viewDiff')}
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
