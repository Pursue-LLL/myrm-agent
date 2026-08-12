import { useTranslations } from 'next-intl';
import { AlertCircle, Loader2 } from 'lucide-react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';

import { type ReportItem } from '../hooks/useCasesEval';

interface HistoryTabProps {
  history: ReportItem[];
  loadingReport: string | null;
  onLoadReport: (filename: string) => void;
}

export default function HistoryTab({ history, loadingReport, onLoadReport }: HistoryTabProps) {
  const t = useTranslations('evalLab');

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
        <AlertCircle className="w-12 h-12 opacity-20" />
        <p>{t('history.noHistory')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="border rounded-lg p-4 bg-card h-[300px]">
        <h3 className="text-sm font-medium mb-4 text-muted-foreground">{t('history.passRateTrend')}</h3>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history} margin={{ top: 5, right: 20, bottom: 25, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
            <XAxis
              dataKey={(d: ReportItem) =>
                d.timestamp ? new Date(d.timestamp * 1000).toLocaleTimeString() : ''
              }
              tick={{ fontSize: 12 }}
            />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
            <RechartsTooltip
              labelFormatter={(l: string) => `${t('history.time')}: ${l}`}
              formatter={(val: number) => [`${Math.round(val)}%`, t('history.passRateLabel')]}
            />
            <Line
              type="monotone"
              dataKey={(d: ReportItem) => (d.total && d.passed != null ? (d.passed / d.total) * 100 : 0)}
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-medium">{t('history.historyRecords')}</h3>
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm text-left min-w-[700px]">
            <thead className="bg-muted/50 border-b">
              <tr>
                <th className="px-4 py-3 font-medium">{t('history.time')}</th>
                <th className="px-4 py-3 font-medium">{t('history.profile')}</th>
                <th className="px-4 py-3 font-medium">{t('report.envModel')}</th>
                <th className="px-4 py-3 font-medium">{t('report.totalCases')}</th>
                <th className="px-4 py-3 font-medium">{t('report.passRate')}</th>
                <th className="px-4 py-3 font-medium">{t('report.avgTime')}</th>
                <th className="px-4 py-3 font-medium">{t('report.avgToken')}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {history
                .slice()
                .reverse()
                .map((h, i) => {
                  const total = h.total ?? 0;
                  const passed = h.passed ?? 0;
                  const rate = total > 0 ? Math.round((passed / total) * 100) : 0;
                  const m = h.manifest;
                  const loading = loadingReport === h.filename;
                  return (
                    <tr
                      key={i}
                      className={`bg-card hover:bg-muted/20 transition-colors cursor-pointer ${loading ? 'opacity-60' : ''}`}
                      onClick={() => onLoadReport(h.filename ?? '')}
                    >
                      <td className="px-4 py-3 flex items-center gap-2">
                        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
                        {h.timestamp ? new Date(h.timestamp * 1000).toLocaleString() : '-'}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs">{m?.profile_id || '-'}</span>
                        {m?.benchmark_mode && (
                          <span className="ml-1 px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 rounded">
                            BM
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {m ? `${m.model_provider}/${m.model_id}` : '-'}
                      </td>
                      <td className="px-4 py-3">{h.total}</td>
                      <td className={`px-4 py-3 font-medium ${rate >= 80 ? 'text-green-500' : 'text-amber-500'}`}>
                        {rate}%
                      </td>
                      <td className="px-4 py-3">{h.avg_time_secs ? h.avg_time_secs.toFixed(2) : '-'}s</td>
                      <td className="px-4 py-3">{Math.round(h.avg_total_tokens || 0)}</td>
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
