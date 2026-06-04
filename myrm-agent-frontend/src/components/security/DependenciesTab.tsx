'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle, CheckCircle, ExternalLink, GitPullRequest } from 'lucide-react';
import { MetricCard, SeverityBadge } from './shared';
import type { SecurityDashboardData } from './types';

interface DependenciesTabProps {
  data: SecurityDashboardData;
  githubTokenConfigured?: boolean;
}

export function DependenciesTab({ data, githubTokenConfigured = false }: DependenciesTabProps) {
  const t = useTranslations('securityDashboard');

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title={t('metricCritical')}
          value={data.metrics.criticalCount}
          icon={AlertTriangle}
          color="bg-red-500/5 border-red-500/20"
        />
        <MetricCard
          title={t('metricHigh')}
          value={data.metrics.highCount}
          icon={AlertTriangle}
          color="bg-orange-500/5 border-orange-500/20"
        />
        <MetricCard
          title={t('metricMedium')}
          value={data.metrics.mediumCount}
          icon={AlertTriangle}
          color="bg-yellow-500/5 border-yellow-500/20"
        />
        <MetricCard
          title={t('metricSecurityPrs')}
          value={data.metrics.securityPrs}
          icon={GitPullRequest}
          color="bg-green-500/5 border-green-500/20"
        />
      </div>

      <div className="rounded-lg border p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          {t('recentAlertsTitle')}
        </h2>
        {data.recentAlerts.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
            <p>{t('noAlerts')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.recentAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-start justify-between p-3 rounded-lg border hover:bg-accent transition-colors"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <SeverityBadge severity={alert.severity} />
                    <span className="text-sm text-muted-foreground">
                      {new Date(alert.createdAt).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="font-medium">{alert.ruleDescription}</p>
                  <p className="text-sm text-muted-foreground mt-1">Rule: {alert.ruleId}</p>
                </div>
                <a
                  href={alert.htmlUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-sm text-primary hover:underline flex-shrink-0"
                >
                  {t('viewOnGithub')}
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <GitPullRequest className="w-5 h-5" />
          {t('dependabotPrsTitle')} ({data.metrics.openDependabotPrs})
        </h2>
            {data.recentPrs.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground space-y-2">
                <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-500" />
                <p>{t('allDepsUpToDate')}</p>
                {data.recentAlerts.length === 0 && (
                  <p className="text-xs max-w-md mx-auto">{t('zeroAlertPrHint')}</p>
                )}
                {!githubTokenConfigured && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">{t('setupToken')}</p>
                )}
              </div>
            ) : (
          <div className="space-y-3">
            {data.recentPrs.map((pr) => (
              <div
                key={pr.number}
                className="flex items-start justify-between p-3 rounded-lg border hover:bg-accent transition-colors"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-muted-foreground">#{pr.number}</span>
                    {pr.labels.includes('security') && (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-red-500/10 text-red-500 border border-red-500/20">
                        {t('securityLabel')}
                      </span>
                    )}
                  </div>
                  <p className="font-medium">{pr.title}</p>
                  <div className="flex items-center gap-2 mt-2">
                    {pr.labels.slice(0, 3).map((label) => (
                      <span key={label} className="px-2 py-0.5 text-xs rounded bg-primary/10 text-primary">
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
                <a
                  href={pr.htmlUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-sm text-primary hover:underline flex-shrink-0"
                >
                  {t('viewOnGithub')}
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
