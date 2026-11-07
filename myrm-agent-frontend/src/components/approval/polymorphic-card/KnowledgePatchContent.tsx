'use client';

import { useTranslations } from 'next-intl';
import type { ApprovalPayload } from '@/store/useApprovalStore';

/** Review body of a proposed knowledge patch: its target, trigger, content, rationale and source queries. */
export function KnowledgePatchContent({ approval }: { approval: ApprovalPayload }) {
  const t = useTranslations('toolApproval');
  const payload = approval.payload ?? {};
  const title = payload.title || approval.reason || t('knowledgePatch.title');
  const targetType = (payload.target_type as string) || 'wiki';
  const content = payload.content || '';
  const trigger = payload.trigger_condition || '';
  const rationale = payload.rationale || '';
  const confidence = typeof payload.confidence === 'number' ? Math.round(payload.confidence * 100) : 80;
  const sourceQueries = Array.isArray(payload.source_queries) ? (payload.source_queries as string[]) : [];

  const targetLabel =
    targetType === 'wiki'
      ? t('knowledgePatch.typeWiki')
      : targetType === 'procedural'
        ? t('knowledgePatch.typeProcedural')
        : t('knowledgePatch.typeSkillGap');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 rounded-lg border bg-muted/40 p-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
            {targetLabel}
          </span>
          <span className="font-semibold text-sm">{title}</span>
        </div>
        <div className="text-xs text-muted-foreground">
          {t('knowledgePatch.confidence')}: <span className="font-semibold">{confidence}%</span>
        </div>
      </div>

      {trigger && (
        <div className="space-y-1">
          <h5 className="font-medium text-xs text-muted-foreground">{t('knowledgePatch.triggerCondition')}</h5>
          <p className="rounded-md bg-muted/30 px-3 py-2 text-xs text-foreground/90">{trigger}</p>
        </div>
      )}

      <div className="space-y-1">
        <h5 className="font-medium text-xs text-muted-foreground">{t('knowledgePatch.content')}</h5>
        <div className="rounded-lg bg-muted p-3 font-mono text-xs whitespace-pre-wrap overflow-x-auto leading-relaxed">
          {content || t('noContent')}
        </div>
      </div>

      {rationale && (
        <div className="space-y-1">
          <h5 className="font-medium text-xs text-muted-foreground">{t('knowledgePatch.rationale')}</h5>
          <p className="text-xs text-muted-foreground italic px-1">{rationale}</p>
        </div>
      )}

      {sourceQueries.length > 0 && (
        <div className="space-y-1">
          <h5 className="font-medium text-xs text-muted-foreground">{t('knowledgePatch.sourceQueries')}</h5>
          <ul className="list-disc list-inside space-y-0.5 text-xs text-muted-foreground px-1">
            {sourceQueries.map((q, idx) => (
              <li key={idx} className="truncate">
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
