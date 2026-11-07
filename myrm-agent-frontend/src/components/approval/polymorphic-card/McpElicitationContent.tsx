'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle } from 'lucide-react';
import type { ApprovalPayload } from '@/store/useApprovalStore';

/** Review body of an MCP server asking the user for input: who asks, the message and the fields it wants. */
export function McpElicitationContent({ approval }: { approval: ApprovalPayload }) {
  const t = useTranslations('toolApproval');
  const serverName = (approval.payload?.server_name as string) || '';
  const elicitMessage = (approval.payload?.message as string) || approval.reason || '';
  const requestedSchema = approval.payload?.requested_schema as Record<string, unknown> | undefined;
  const schemaProperties = (requestedSchema?.properties ?? {}) as Record<
    string,
    { type?: string; description?: string }
  >;
  const hasFields = Object.keys(schemaProperties).length > 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3">
        <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <h4 className="font-semibold text-sm">{t('mcpElicitationTitle')}</h4>
          {serverName && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {t('mcpElicitationServer')}: <span className="font-mono">{serverName}</span>
            </p>
          )}
        </div>
      </div>
      <p className="text-sm text-foreground">{elicitMessage}</p>
      {hasFields && (
        <div className="rounded-lg bg-muted p-3 space-y-1">
          {Object.entries(schemaProperties).map(([field, meta]) => (
            <div key={field} className="text-xs font-mono">
              <span className="text-primary">{field}</span>
              {meta.type && <span className="text-muted-foreground"> ({meta.type})</span>}
              {meta.description && <span className="text-muted-foreground">: {meta.description}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
