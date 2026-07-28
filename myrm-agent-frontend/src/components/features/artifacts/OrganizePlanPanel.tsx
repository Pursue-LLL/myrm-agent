'use client';

/**
 * Organize plan HITL review panel
 *
 * [INPUT]
 * - @/services/organize apply/rollback/latest-job API
 * - organizePlanUtils parse/edit helpers
 *
 * [OUTPUT]
 * - OrganizePlanPanel: editable from→to table + Validate / Apply / Rollback actions
 *
 * [POS]
 * WebUI HITL surface for *.organize-plan.json artifacts. User edits plan before batch move.
 * Apply/Rollback success dispatches workspace-file-changed for sidebar tree refresh.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { applyOrganizePlan, fetchLatestOrganizeJob, rollbackOrganizeJob } from '@/services/organize';
import type { OrganizePlanDto } from '@/services/organizeTypes';
import {
  parseOrganizePlan,
  removeOrganizePlanItem,
  serializeOrganizePlan,
  updateOrganizePlanItem,
} from './organizePlanUtils';

function notifyWorkspaceFilesChanged(workspacePath: string): void {
  if (!workspacePath) return;
  window.dispatchEvent(
    new CustomEvent('workspace-file-changed', {
      detail: { workspace_path: workspacePath },
    }),
  );
}

interface OrganizePlanPanelProps {
  workspace: string;
  planContent: string;
  onPlanChange?: (content: string) => void;
  onComplete?: () => void;
}

export const OrganizePlanPanel: React.FC<OrganizePlanPanelProps> = ({
  workspace,
  planContent,
  onPlanChange,
  onComplete,
}) => {
  const t = useTranslations('artifacts.organizePlan');
  const [plan, setPlan] = useState<OrganizePlanDto | null>(() => parseOrganizePlan(planContent));
  const [loading, setLoading] = useState(false);
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  useEffect(() => {
    setPlan(parseOrganizePlan(planContent));
  }, [planContent]);

  useEffect(() => {
    if (!workspace) return;
    void fetchLatestOrganizeJob(workspace).then((res) => {
      if (res.job?.jobId) {
        setLastJobId(res.job.jobId);
      }
    });
  }, [workspace]);

  const itemCount = plan?.items.length ?? 0;

  const syncPlan = useCallback(
    (next: OrganizePlanDto) => {
      setPlan(next);
      onPlanChange?.(serializeOrganizePlan(next));
    },
    [onPlanChange],
  );

  const handlePreview = useCallback(async () => {
    if (!plan || !workspace) {
      toast.error(t('workspaceMissing'));
      return;
    }
    setLoading(true);
    try {
      const result = await applyOrganizePlan(workspace, plan, true);
      if (!result.ok) {
        const first = result.issues?.[0];
        toast.error(first?.message ?? t('validateFailed'));
        return;
      }
      toast.success(t('previewOk', { count: result.appliedCount ?? 0 }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('validateFailed'));
    } finally {
      setLoading(false);
    }
  }, [plan, workspace, t]);

  const handleApply = useCallback(async () => {
    if (!plan || !workspace) {
      toast.error(t('workspaceMissing'));
      return;
    }
    setLoading(true);
    try {
      const result = await applyOrganizePlan(workspace, plan, false);
      if (!result.ok) {
        const first = result.issues?.[0];
        toast.error(first?.message ?? t('applyFailed'));
        return;
      }
      if (result.jobId) {
        setLastJobId(result.jobId);
      }
      toast.success(t('applyOk', { count: result.appliedCount ?? 0 }));
      notifyWorkspaceFilesChanged(workspace);
      onComplete?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('applyFailed'));
    } finally {
      setLoading(false);
    }
  }, [plan, workspace, t, onComplete]);

  const handleRollback = useCallback(async () => {
    if (!lastJobId) {
      toast.error(t('noJob'));
      return;
    }
    setLoading(true);
    try {
      const result = await rollbackOrganizeJob(lastJobId);
      if (result.jobStatus === 'partial_rollback') {
        toast.warning(t('rollbackPartial', { count: result.appliedCount ?? 0 }));
      } else {
        toast.success(t('rollbackOk', { count: result.appliedCount ?? 0 }));
      }
      setLastJobId(null);
      notifyWorkspaceFilesChanged(workspace);
      onComplete?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('rollbackFailed'));
    } finally {
      setLoading(false);
    }
  }, [lastJobId, workspace, t, onComplete]);

  const rows = useMemo(() => plan?.items ?? [], [plan]);

  if (!plan) {
    return <p className="text-xs text-muted-foreground px-1">{t('invalidPlan')}</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t('hint', { scope: plan.scope_root, count: itemCount })}</p>
      <p className="text-xs text-muted-foreground/90 leading-snug">{t('undoHint')}</p>
      <div className="max-h-56 overflow-x-auto overflow-y-auto rounded-md border border-border/60">
        <table className="w-full min-w-[32rem] text-xs">
          <thead className="sticky top-0 bg-muted/80">
            <tr>
              <th className="px-2 py-1 text-left font-medium">{t('colFrom')}</th>
              <th className="px-2 py-1 text-left font-medium">{t('colTo')}</th>
              <th className="px-2 py-1 text-left font-medium">{t('colReason')}</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((item, index) => (
              <tr key={`${item.src}-${index}`} className="border-t border-border/40">
                <td className="px-2 py-1 align-top break-all">{item.src}</td>
                <td className="px-2 py-1 align-top">
                  <Input
                    value={item.dst}
                    onChange={(e) => syncPlan(updateOrganizePlanItem(plan, index, { dst: e.target.value }))}
                    className="h-7 text-xs"
                  />
                </td>
                <td className="px-2 py-1 align-top text-muted-foreground">{item.reason}</td>
                <td className="px-1 py-1 align-top">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => syncPlan(removeOrganizePlanItem(plan, index))}
                  >
                    {t('removeRow')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button type="button" size="sm" variant="outline" disabled={loading} className="w-full sm:w-auto" onClick={() => void handlePreview()}>
          {t('preview')}
        </Button>
        <Button type="button" size="sm" disabled={loading || itemCount === 0} className="w-full sm:w-auto" onClick={() => void handleApply()}>
          {t('apply')}
        </Button>
        {lastJobId ? (
          <Button type="button" size="sm" variant="secondary" disabled={loading} className="w-full sm:w-auto" onClick={() => void handleRollback()}>
            {t('rollback')}
          </Button>
        ) : null}
      </div>
    </div>
  );
};
