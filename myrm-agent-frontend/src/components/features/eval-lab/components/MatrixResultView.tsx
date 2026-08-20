import React from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, XCircle, AlertCircle, Minus, ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface MatrixProfileResult {
  pass_count: number;
  fail_count: number;
  error_count: number;
  pass_rate: number;
  total_tokens: number;
  total_cost: number;
  total_ms: number;
  memory_tool_calls?: number;
  total_tool_calls?: number;
  limit_hits?: number;
  blocked_count?: number;
  agent_model?: string;
}

interface MatrixCell {
  passed: boolean | null;
  total_ms: number;
  token_usage: Record<string, number>;
  cost: number;
  error: string | null;
  tool_calls?: number;
  limit_reached?: string | null;
  blocked_count?: number;
}

interface MatrixRow {
  case_index: number;
  message: string;
  profiles: Record<string, MatrixCell>;
}

export interface LayerMeta {
  key: string;
  benchmark_mode: boolean;
  skills_enabled: boolean;
  memory_enabled: boolean;
  fingerprint: string;
}

export interface MatrixReportData {
  profile_ids: string[];
  total_cases: number;
  stable_count: number;
  regression_count: number;
  stable_rate: number;
  per_profile: Record<string, MatrixProfileResult>;
  matrix: MatrixRow[];
  total_ms: number;
  layers?: LayerMeta[];
  agent_model?: string;
  judge_model?: string;
  harness_version?: string;
  eval_type?: string;
  profile_id?: string;
  aborted?: boolean;
  limit?: number | null;
  max_tool_calls?: number;
  max_iterations?: number;
  decontam_active?: boolean;
}

interface Props {
  report: MatrixReportData;
  profileNames?: Record<string, string>;
}

export default function MatrixResultView({ report, profileNames }: Props) {
  const t = useTranslations('evalLab.matrix');
  const tLayers = useTranslations('evalLab.layers');

  const layers = report.layers ?? [];
  const isLayered = layers.length > 0;

  const getProfileLabel = (pid: string) => {
    if (isLayered) {
      return tLayers(`${pid}.label`);
    }
    return profileNames?.[pid] || pid.slice(0, 8);
  };

  // Delta pass rate against the previous layer (null for the first layer).
  const deltaFor = (index: number): number | null => {
    if (!isLayered || index === 0) {
      return null;
    }
    const prev = report.per_profile[layers[index - 1].key]?.pass_rate;
    const cur = report.per_profile[layers[index].key]?.pass_rate;
    return prev != null && cur != null ? (cur - prev) * 100 : null;
  };

  const failedAllCount = report.total_cases - report.stable_count - report.regression_count;
  const showMemoryCalls = report.profile_ids.some((pid) => report.per_profile[pid]?.memory_tool_calls != null);
  const showToolCalls = report.profile_ids.some((pid) => report.per_profile[pid]?.total_tool_calls != null);

  return (
    <div className="space-y-6 max-w-full mx-auto overflow-x-auto">
      {report.aborted && (
        <div className="p-3 rounded-lg border border-amber-500/40 bg-amber-50 dark:bg-amber-900/10 text-amber-700 dark:text-amber-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {tLayers('abortedNotice')}
        </div>
      )}
      {report.limit != null && (
        <div className="flex items-center gap-1.5 text-xs">
          <span
            className="px-2 py-1 rounded-md bg-violet-500/10 text-violet-600 dark:text-violet-400 font-medium"
            title={t('sampledTitle')}
          >
            {t('sampled')} · {report.limit}
          </span>
          <span className="text-muted-foreground">{t('sampledHint')}</span>
        </div>
      )}
      {report.max_tool_calls != null && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="px-2 py-1 rounded-md bg-primary/10 text-primary font-medium">
            {t('budget')} · {report.max_tool_calls} {t('budgetToolCalls')} /{' '}
            {report.max_iterations != null ? `${report.max_iterations} ${t('budgetIterations')}` : '-'}
          </span>
          <span className="text-muted-foreground">{t('budgetHint')}</span>
        </div>
      )}
      {(report.profile_id && report.eval_type !== 'matrix') ||
      report.harness_version ||
      typeof report.decontam_active === 'boolean' ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground px-1">
          {report.profile_id && report.eval_type !== 'matrix' && (
            <span>
              {tLayers('basedOnProfile')}: {profileNames?.[report.profile_id] || report.profile_id}
            </span>
          )}
          {report.harness_version && (
            <span className="font-mono">
              {tLayers('harnessVersion')}: {report.harness_version}
            </span>
          )}
          {typeof report.decontam_active === 'boolean' && (
            <span
              className={`px-2 py-0.5 rounded-md font-medium ${
                report.decontam_active
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {report.decontam_active ? tLayers('decontamOn') : tLayers('decontamOff')}
            </span>
          )}
        </div>
      ) : null}
      {isLayered && (
        <div className="p-4 rounded-lg border bg-gradient-to-br from-card to-muted/30">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{tLayers('title')}</span>
              <span className="text-xs text-muted-foreground">{tLayers('desc')}</span>
            </div>
            {(report.agent_model || report.judge_model) && (
              <div className="flex flex-wrap gap-2 text-xs">
                {report.agent_model && report.agent_model !== 'unknown' && (
                  <span className="px-2 py-1 rounded-md bg-muted font-mono">
                    {tLayers('scoredModel')}: {report.agent_model}
                  </span>
                )}
                {report.judge_model && report.judge_model !== 'none' && (
                  <span className="px-2 py-1 rounded-md bg-muted font-mono">
                    {tLayers('judgeModel')}: {report.judge_model}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('totalCases')}</span>
          <span className="text-3xl font-bold mt-1">{report.total_cases}</span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('stableRate')}</span>
          <span
            className={`text-3xl font-bold mt-1 ${report.stable_rate >= 0.8 ? 'text-green-500' : 'text-amber-500'}`}
          >
            {Math.round(report.stable_rate * 100)}%
          </span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('regressionCount')}</span>
          <span
            className={`text-3xl font-bold mt-1 ${report.regression_count > 0 ? 'text-amber-500' : 'text-green-500'}`}
          >
            {report.regression_count}
          </span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('totalTime')}</span>
          <span className="text-3xl font-bold mt-1">{(report.total_ms / 1000).toFixed(1)}s</span>
        </div>
      </div>

      {/* Per-profile summary */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-muted/50 border-b">
            <tr>
              <th className="px-4 py-3 font-medium">{isLayered ? tLayers('layer') : t('profile')}</th>
              <th className="px-4 py-3 font-medium">{isLayered ? tLayers('config') : t('passRate')}</th>
              <th className="px-4 py-3 font-medium">{t('passRate')}</th>
              {isLayered && <th className="px-4 py-3 font-medium">{tLayers('delta')}</th>}
              <th className="px-4 py-3 font-medium">{t('passed')}</th>
              <th className="px-4 py-3 font-medium">{t('failed')}</th>
              <th className="px-4 py-3 font-medium">{t('tokens')}</th>
              <th className="px-4 py-3 font-medium">{t('cost')}</th>
              {isLayered && <th className="px-4 py-3 font-medium">{tLayers('costEfficiency')}</th>}
              <th className="px-4 py-3 font-medium">{t('time')}</th>
              {showMemoryCalls && <th className="px-4 py-3 font-medium">{t('memoryCalls')}</th>}
              {showToolCalls && (
                <>
                  <th className="px-4 py-3 font-medium">{t('toolCalls')}</th>
                  <th className="px-4 py-3 font-medium">{t('limitHits')}</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y">
            {report.profile_ids.map((pid, index) => {
              const pr = report.per_profile[pid];
              if (!pr) {
                return null;
              }
              const rate = Math.round(pr.pass_rate * 100);
              const delta = deltaFor(index);
              const efficiency = pr.total_cost > 0 ? (pr.pass_rate * 100) / pr.total_cost : null;
              return (
                <tr key={pid} className="bg-card hover:bg-muted/20">
                  <td className="px-4 py-3 font-mono text-xs">{getProfileLabel(pid)}</td>
                  <td className="px-4 py-3">
                    {isLayered && layers[index] ? (
                      <span className="text-xs text-muted-foreground">
                        {[
                          layers[index].memory_enabled ? tLayers('memoryOn') : tLayers('memoryOff'),
                          layers[index].skills_enabled ? tLayers('skillsOn') : tLayers('skillsOff'),
                        ].join(' · ')}
                      </span>
                    ) : pr.agent_model && pr.agent_model !== 'unknown' ? (
                      <span className="text-xs text-muted-foreground font-mono">{pr.agent_model}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 font-medium ${rate >= 80 ? 'text-green-500' : 'text-amber-500'}`}>
                    {rate}%
                  </td>
                  {isLayered && (
                    <td className="px-4 py-3">
                      {delta === null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <span
                          className={`inline-flex items-center gap-0.5 font-medium ${delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-600' : 'text-muted-foreground'}`}
                        >
                          {delta > 0 ? (
                            <ArrowUpRight className="w-3.5 h-3.5" />
                          ) : delta < 0 ? (
                            <ArrowDownRight className="w-3.5 h-3.5" />
                          ) : null}
                          {delta >= 0 ? '+' : ''}
                          {delta.toFixed(1)}%
                        </span>
                      )}
                    </td>
                  )}
                  <td className="px-4 py-3 text-green-600">{pr.pass_count}</td>
                  <td className="px-4 py-3 text-red-600">{pr.fail_count + pr.error_count}</td>
                  <td className="px-4 py-3">{pr.total_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3">${pr.total_cost.toFixed(4)}</td>
                  {isLayered && (
                    <td className="px-4 py-3">
                      {efficiency === null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <span className="font-medium">{efficiency.toFixed(1)} pts/US$</span>
                      )}
                    </td>
                  )}
                  <td className="px-4 py-3">{(pr.total_ms / 1000).toFixed(1)}s</td>
                  {showMemoryCalls && <td className="px-4 py-3">{pr.memory_tool_calls ?? 0}</td>}
                  {showToolCalls && (
                    <>
                      <td className="px-4 py-3">{pr.total_tool_calls ?? 0}</td>
                      <td className="px-4 py-3">
                        {(pr.limit_hits ?? 0) > 0 ? (
                          <span className="px-1.5 py-0.5 rounded-md bg-amber-500/15 text-amber-600 dark:text-amber-400 text-xs font-medium">
                            {pr.limit_hits}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {isLayered && (
        <div className="text-xs text-muted-foreground px-1 space-y-1">
          <div>{tLayers('fingerprint')}</div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono">
            {layers.map((layer) => (
              <span key={layer.key}>
                {getProfileLabel(layer.key)}: {layer.fingerprint}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Matrix grid */}
      <div className="border rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-muted/50 border-b flex items-center justify-between">
          <h3 className="text-sm font-medium">{t('matrixDetail')}</h3>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-green-100 dark:bg-green-900/30 border border-green-300 dark:border-green-700" />
              {t('legend.stable')} ({report.stable_count})
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-amber-100 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700" />
              {t('legend.regression')} ({report.regression_count})
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700" />
              {t('legend.allFailed')} ({failedAllCount})
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left min-w-[600px]">
            <thead className="bg-muted/30 border-b">
              <tr>
                <th className="px-4 py-2 font-medium w-[40%]">{t('case')}</th>
                {report.profile_ids.map((pid) => (
                  <th key={pid} className="px-4 py-2 font-medium text-center font-mono text-xs">
                    {getProfileLabel(pid)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {report.matrix.map((row) => {
                const cells = report.profile_ids.map((pid) => row.profiles[pid]);
                const allPass = cells.every((c) => c?.passed === true);
                const someFail = cells.some((c) => c?.passed === false || c?.error);
                const somePass = cells.some((c) => c?.passed === true);
                const isRegression = somePass && someFail;

                let rowBg = '';
                if (allPass) {
                  rowBg = 'bg-green-50 dark:bg-green-900/10';
                } else if (isRegression) {
                  rowBg = 'bg-amber-50 dark:bg-amber-900/10';
                } else if (someFail) {
                  rowBg = 'bg-red-50 dark:bg-red-900/10';
                }

                return (
                  <tr key={row.case_index} className={`${rowBg} hover:bg-muted/20 transition-colors`}>
                    <td className="px-4 py-2 truncate max-w-xs" title={row.message}>
                      <span className="text-muted-foreground mr-2">#{row.case_index + 1}</span>
                      {row.message.slice(0, 60)}
                    </td>
                    {report.profile_ids.map((pid) => {
                      const cell = row.profiles[pid];
                      if (!cell) {
                        return (
                          <td key={pid} className="px-4 py-2 text-center">
                            <Minus className="w-4 h-4 mx-auto text-muted-foreground" />
                          </td>
                        );
                      }
                      return (
                        <td key={pid} className="px-4 py-2 text-center">
                          {cell.passed === true ? (
                            <CheckCircle2 className="w-4 h-4 mx-auto text-green-600" />
                          ) : cell.error ? (
                            <AlertCircle className="w-4 h-4 mx-auto text-red-600" />
                          ) : (
                            <XCircle className="w-4 h-4 mx-auto text-red-500" />
                          )}
                          <span className="text-[10px] text-muted-foreground block mt-0.5">
                            {(cell.total_ms / 1000).toFixed(1)}s
                          </span>
                          {(cell.tool_calls != null || cell.limit_reached || cell.blocked_count) && (
                            <span className="flex items-center justify-center gap-1 mt-1">
                              {cell.limit_reached && (
                                <span
                                  className="px-1 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 text-[9px] font-semibold"
                                  title={`${t('limitHitTitle')} · ${cell.limit_reached}`}
                                >
                                  {t('limitHits')}
                                </span>
                              )}
                              {cell.tool_calls != null && (
                                <span className="text-[9px] text-muted-foreground" title={t('toolCallsTitle')}>
                                  {cell.tool_calls}×
                                </span>
                              )}
                              {(cell.blocked_count ?? 0) > 0 && (
                                <span
                                  className="px-1 rounded bg-violet-500/15 text-violet-600 dark:text-violet-400 text-[9px] font-semibold"
                                  title={t('blockedTitle')}
                                >
                                  {t('blocked')} {cell.blocked_count}
                                </span>
                              )}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
