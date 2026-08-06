'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { fetchWorkflowTemplateDetail } from '@/services/workflowTemplates';

interface WorkflowTemplateScriptPreviewProps {
  templateId: string;
  className?: string;
}

const WorkflowTemplateScriptPreview = memo(
  ({ templateId, className }: WorkflowTemplateScriptPreviewProps) => {
    const t = useTranslations('settings.skills.workflowTemplates');
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [scriptCode, setScriptCode] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleToggle = useCallback(async () => {
      if (open) {
        setOpen(false);
        return;
      }
      setOpen(true);
      if (scriptCode !== null || loading) {
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const detail = await fetchWorkflowTemplateDetail(templateId);
        setScriptCode(detail.script_code);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('previewLoadFailed'));
      } finally {
        setLoading(false);
      }
    }, [loading, open, scriptCode, t, templateId]);

    return (
      <div className={cn('mt-2', className)}>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 gap-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => void handleToggle()}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {t('previewScript')}
        </Button>
        {open ? (
          <div className="mt-2 rounded-lg border border-border/50 bg-muted/30 p-3">
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t('previewLoading')}
              </div>
            ) : null}
            {!loading && error ? <p className="text-xs text-destructive">{error}</p> : null}
            {!loading && !error && scriptCode ? (
              <pre className="max-h-64 overflow-auto text-[11px] leading-relaxed font-mono text-foreground/90 whitespace-pre-wrap break-all">
                {scriptCode}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  },
);

WorkflowTemplateScriptPreview.displayName = 'WorkflowTemplateScriptPreview';

export default WorkflowTemplateScriptPreview;
