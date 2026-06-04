'use client';

import { useTranslations } from 'next-intl';
import { Activity, CheckCircle } from 'lucide-react';
import type { RateLimitStatus } from './types';

interface RateLimitTabProps {
  rateLimitData: RateLimitStatus[];
  rateLimitLive: boolean;
}

export function RateLimitTab({ rateLimitData, rateLimitLive }: RateLimitTabProps) {
  const t = useTranslations('securityDashboard');

  return (
    <div className="rounded-lg border p-6">
      <div className="flex items-start justify-between mb-4">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5" />
          {t('rateLimitMonitorTitle')}
        </h2>
        <div className="px-3 py-1 text-xs rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20">
          {rateLimitLive ? t('rateLimitLive') : t('rateLimitUnavailable')}
        </div>
      </div>

      {rateLimitData.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
          <p>{t('noRateLimits')}</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColUser')}
                </th>
                <th className="text-left py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColResource')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColCurrent')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColMax')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColRemaining')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColWindow')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-sm text-muted-foreground">
                  {t('rateLimitColUsage')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rateLimitData.map((status, idx) => {
                const usagePercent = status.max > 0 ? (status.current / status.max) * 100 : 0;
                const isHigh = usagePercent > 80;

                return (
                  <tr key={idx} className="border-b hover:bg-accent transition-colors">
                    <td className="py-3 px-4 font-mono text-sm">{status.userId}</td>
                    <td className="py-3 px-4 text-sm">{status.resource}</td>
                    <td className="py-3 px-4 text-right font-mono text-sm">{status.current}</td>
                    <td className="py-3 px-4 text-right font-mono text-sm">{status.max}</td>
                    <td className="py-3 px-4 text-right font-mono text-sm">
                      <span className={isHigh ? 'text-red-500 font-semibold' : ''}>{status.remaining}</span>
                    </td>
                    <td className="py-3 px-4 text-right text-sm text-muted-foreground">
                      {Math.floor(status.windowSeconds / 60)}
                      {t('rateLimitMinutes')}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all ${isHigh ? 'bg-red-500' : 'bg-green-500'}`}
                            style={{ width: `${Math.min(usagePercent, 100)}%` }}
                          />
                        </div>
                        <span
                          className={`text-xs font-medium ${isHigh ? 'text-red-500' : 'text-muted-foreground'}`}
                        >
                          {usagePercent.toFixed(0)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
