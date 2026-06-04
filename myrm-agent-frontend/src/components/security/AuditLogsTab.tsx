'use client';

import { useTranslations } from 'next-intl';
import { CheckCircle, FileText } from 'lucide-react';
import type { AuditLogEvent } from './types';

interface AuditLogsTabProps {
  auditLive: boolean;
  auditLogData: AuditLogEvent[];
  filteredAuditLogData: AuditLogEvent[];
  searchUserId: string;
  searchEventType: string;
  searchResult: 'all' | 'success' | 'failed';
  onSearchUserIdChange: (value: string) => void;
  onSearchEventTypeChange: (value: string) => void;
  onSearchResultChange: (value: 'all' | 'success' | 'failed') => void;
}

export function AuditLogsTab({
  auditLive,
  auditLogData,
  filteredAuditLogData,
  searchUserId,
  searchEventType,
  searchResult,
  onSearchUserIdChange,
  onSearchEventTypeChange,
  onSearchResultChange,
}: AuditLogsTabProps) {
  const t = useTranslations('securityDashboard');

  return (
    <div className="rounded-lg border p-6">
      <div className="flex items-start justify-between mb-4">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5" />
          {t('auditLogsTitle')}
        </h2>
        <div
          className={`px-3 py-1 text-xs rounded-full border ${
            auditLive
              ? 'bg-green-500/10 text-green-600 border-green-500/20'
              : 'bg-muted text-muted-foreground border-border'
          }`}
        >
          {auditLive ? t('auditLive') : t('auditOffline')}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 p-4 rounded-lg bg-muted/50">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterUserId')}</label>
          <input
            type="text"
            value={searchUserId}
            onChange={(e) => onSearchUserIdChange(e.target.value)}
            placeholder={t('auditFilterUserIdPlaceholder')}
            className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterEventType')}</label>
          <input
            type="text"
            value={searchEventType}
            onChange={(e) => onSearchEventTypeChange(e.target.value)}
            placeholder={t('auditFilterEventTypePlaceholder')}
            className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">{t('auditFilterResult')}</label>
          <select
            value={searchResult}
            onChange={(e) => onSearchResultChange(e.target.value as 'all' | 'success' | 'failed')}
            className="w-full px-3 py-2 text-sm rounded-full border bg-background focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">{t('auditFilterAll')}</option>
            <option value="success">{t('auditFilterSuccess')}</option>
            <option value="failed">{t('auditFilterFailed')}</option>
          </select>
        </div>
      </div>

      <div className="text-xs text-muted-foreground mb-2">
        {t('auditShowingCount', { shown: filteredAuditLogData.length, total: auditLogData.length })}
      </div>

      {filteredAuditLogData.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <CheckCircle className="w-12 h-12 mx-auto mb-2 text-gray-400" />
          <p>{auditLogData.length > 0 ? t('auditNoMatch') : t('auditEmpty')}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredAuditLogData.map((event, idx) => {
            const isSuccess = event.result === 'success';
            return (
              <div
                key={idx}
                className={`p-3 rounded-lg border transition-colors ${
                  isSuccess ? 'hover:bg-green-500/5' : 'hover:bg-red-500/5'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded border ${
                          isSuccess
                            ? 'bg-green-500/10 text-green-500 border-green-500/20'
                            : 'bg-red-500/10 text-red-500 border-red-500/20'
                        }`}
                      >
                        {event.event_type}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(event.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-sm space-y-1 mt-2">
                      {event.user_id && (
                        <p>
                          <span className="text-muted-foreground">{t('auditFieldUser')}:</span>{' '}
                          <span className="font-mono">{event.user_id}</span>
                        </p>
                      )}
                      {event.ip_address && (
                        <p>
                          <span className="text-muted-foreground">{t('auditFieldIp')}:</span>{' '}
                          <span className="font-mono">{event.ip_address}</span>
                        </p>
                      )}
                      {event.action && (
                        <p>
                          <span className="text-muted-foreground">{t('auditFieldAction')}:</span>{' '}
                          <span>{event.action}</span>
                        </p>
                      )}
                      {event.result && (
                        <p>
                          <span className="text-muted-foreground">{t('auditFieldResult')}:</span>{' '}
                          <span className={isSuccess ? 'text-green-500' : 'text-red-500'}>{event.result}</span>
                        </p>
                      )}
                      {event.metadata && Object.keys(event.metadata).length > 0 && (
                        <details className="mt-2">
                          <summary className="text-xs text-muted-foreground cursor-pointer hover:underline">
                            {t('auditFieldMetadata')}
                          </summary>
                          <pre className="text-xs bg-muted p-2 rounded mt-1 overflow-x-auto">
                            {JSON.stringify(event.metadata, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                  {event.trace_id && (
                    <div className="text-xs text-muted-foreground font-mono flex-shrink-0 ml-4">
                      trace: {event.trace_id.slice(0, 8)}...
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
