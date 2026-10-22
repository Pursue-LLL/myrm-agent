'use client';

/**
 * [INPUT]
 * @/store/chat/useSubagentStore::SubagentNode (POS: Multi-agent execution tree and stream state store)
 *
 * [OUTPUT]
 * SubagentErrorNotice: Failure panel for a subagent node; a `blocked` node gets a localized review note instead of the raw error text.
 *
 * [POS]
 * Subagent inspection surface. A blocked node means verification reached no conclusion, so it is presented as "needs review" (amber) and not as a failure (red).
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, XCircle } from 'lucide-react';
import type { SubagentNode } from '@/store/chat/useSubagentStore';

interface SubagentErrorNoticeProps {
  node: Pick<SubagentNode, 'status' | 'error'>;
}

export const SubagentErrorNotice: React.FC<SubagentErrorNoticeProps> = ({ node }) => {
  const t = useTranslations('subagentDashboard');

  if (node.status === 'blocked') {
    return (
      <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/60 text-amber-800 dark:text-amber-300 text-xs">
        <div className="flex items-center gap-1.5 font-bold mb-1">
          <ShieldAlert className="w-4 h-4 shrink-0" />
          <span>{t('statusLabel.blocked')}</span>
        </div>
        <p className="leading-relaxed">{t('detailBlockedNote')}</p>
      </div>
    );
  }

  if (!node.error) {
    return null;
  }

  return (
    <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 text-xs">
      <div className="flex items-center gap-1.5 font-bold mb-1">
        <XCircle className="w-4 h-4" />
        <span>{t('detailErrorDiagnostic')}</span>
      </div>
      <pre className="font-mono text-[11px] whitespace-pre-wrap break-all overflow-x-auto bg-black/5 dark:bg-black/30 p-2 rounded">
        {node.error}
      </pre>
    </div>
  );
};
