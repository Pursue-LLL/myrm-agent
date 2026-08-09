import React from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, XCircle, AlertCircle, Minus } from 'lucide-react';

interface MatrixProfileResult {
  pass_count: number;
  fail_count: number;
  error_count: number;
  pass_rate: number;
  total_tokens: number;
  total_cost: number;
  total_ms: number;
  memory_tool_calls?: number;
}

interface MatrixCell {
  passed: boolean | null;
  total_ms: number;
  token_usage: Record<string, number>;
  cost: number;
  error: string | null;
}

interface MatrixRow {
  case_index: number;
  message: string;
  profiles: Record<string, MatrixCell>;
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
}

interface Props {
  report: MatrixReportData;
  profileNames?: Record<string, string>;
}

export default function MatrixResultView({ report, profileNames }: Props) {
  const t = useTranslations('evalLab.matrix');

  const getProfileLabel = (pid: string) => profileNames?.[pid] || pid.slice(0, 8);
  const failedAllCount = report.total_cases - report.stable_count - report.regression_count;
  const showMemoryCalls = report.profile_ids.some((pid) => report.per_profile[pid]?.memory_tool_calls != null);

  return (
    <div className="space-y-6 max-w-full mx-auto overflow-x-auto">
      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('totalCases')}</span>
          <span className="text-3xl font-bold mt-1">{report.total_cases}</span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('stableRate')}</span>
          <span
            className={`text-3xl font-bold mt-1 ${
              report.stable_rate >= 0.8 ? 'text-green-500' : 'text-amber-500'
            }`}
          >
            {Math.round(report.stable_rate * 100)}%
          </span>
        </div>
        <div className="p-4 border rounded-lg bg-card flex flex-col items-center">
          <span className="text-sm text-muted-foreground">{t('regressionCount')}</span>
          <span className={`text-3xl font-bold mt-1 ${report.regression_count > 0 ? 'text-amber-500' : 'text-green-500'}`}>
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
              <th className="px-4 py-3 font-medium">{t('profile')}</th>
              <th className="px-4 py-3 font-medium">{t('passRate')}</th>
              <th className="px-4 py-3 font-medium">{t('passed')}</th>
              <th className="px-4 py-3 font-medium">{t('failed')}</th>
              <th className="px-4 py-3 font-medium">{t('tokens')}</th>
              <th className="px-4 py-3 font-medium">{t('cost')}</th>
              <th className="px-4 py-3 font-medium">{t('time')}</th>
              {showMemoryCalls && <th className="px-4 py-3 font-medium">{t('memoryCalls')}</th>}
            </tr>
          </thead>
          <tbody className="divide-y">
            {report.profile_ids.map((pid) => {
              const pr = report.per_profile[pid];
              if (!pr) return null;
              const rate = Math.round(pr.pass_rate * 100);
              return (
                <tr key={pid} className="bg-card hover:bg-muted/20">
                  <td className="px-4 py-3 font-mono text-xs">{getProfileLabel(pid)}</td>
                  <td className={`px-4 py-3 font-medium ${rate >= 80 ? 'text-green-500' : 'text-amber-500'}`}>
                    {rate}%
                  </td>
                  <td className="px-4 py-3 text-green-600">{pr.pass_count}</td>
                  <td className="px-4 py-3 text-red-600">{pr.fail_count + pr.error_count}</td>
                  <td className="px-4 py-3">{pr.total_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3">${pr.total_cost.toFixed(4)}</td>
                  <td className="px-4 py-3">{(pr.total_ms / 1000).toFixed(1)}s</td>
                  {showMemoryCalls && (
                    <td className="px-4 py-3">{pr.memory_tool_calls ?? 0}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

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
                if (allPass) rowBg = 'bg-green-50 dark:bg-green-900/10';
                else if (isRegression) rowBg = 'bg-amber-50 dark:bg-amber-900/10';
                else if (someFail) rowBg = 'bg-red-50 dark:bg-red-900/10';

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
