'use client';

/**
 * [INPUT]
 * @/services/cron::CronJob (POS: Cron job API types)
 * next/link (POS: client navigation to Settings workflow library)
 *
 * [OUTPUT]
 * CronWorkflowTemplateBadge, CronWorkflowTemplateDetail: read-only template binding display; invalid bindings use amber Badge.
 *
 * [POS]
 * Cron list cards and compact surfaces. Links to Settings workflow template library.
 */

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Route } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import type { CronJob } from '@/services/cron';

const LIBRARY_HREF = '/settings/skills?sub=workflowTemplates';

type CronWorkflowTemplateJob = Pick<
  CronJob,
  'workflow_template_id' | 'workflow_template_args' | 'workflow_template_display_name'
>;

function formatTemplateArgs(args: Record<string, string> | null | undefined): string {
  if (!args) {return '';}
  return Object.entries(args)
    .filter(([, value]) => value.trim().length > 0)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ');
}

function isCronWorkflowTemplateBindingInvalid(job: CronWorkflowTemplateJob): boolean {
  const templateId = job.workflow_template_id?.trim();
  if (!templateId) {return false;}
  return !job.workflow_template_display_name?.trim();
}

function resolveTemplateLabel(job: CronWorkflowTemplateJob): string {
  const templateId = job.workflow_template_id?.trim();
  if (!templateId) {return '';}
  return job.workflow_template_display_name?.trim() || templateId;
}

export function CronWorkflowTemplateBadge({ job }: { job: CronWorkflowTemplateJob }) {
  const t = useTranslations('cron');
  const templateId = job.workflow_template_id?.trim();
  if (!templateId) {return null;}

  const bindingInvalid = isCronWorkflowTemplateBindingInvalid(job);
  const label = resolveTemplateLabel(job);
  const argsSummary = formatTemplateArgs(job.workflow_template_args);

  if (bindingInvalid) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400"
            onClick={(event) => event.stopPropagation()}
          >
            <Route className="h-3 w-3 shrink-0" />
            <span className="truncate max-w-[120px]">{templateId}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent>{t('workflowTemplateUnavailable')}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link href={LIBRARY_HREF} onClick={(event) => event.stopPropagation()}>
          <span className="inline-flex items-center gap-0.5 text-teal-600 dark:text-teal-400 hover:underline">
            <Route className="h-3 w-3 shrink-0" />
            <span className="truncate max-w-[120px]">{label}</span>
          </span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>
        {argsSummary
          ? t('workflowTemplateTooltipWithArgs', { template: label, args: argsSummary })
          : t('workflowTemplateTooltip', { template: label })}
      </TooltipContent>
    </Tooltip>
  );
}

export function CronWorkflowTemplateDetail({ job }: { job: CronWorkflowTemplateJob }) {
  const t = useTranslations('cron');
  const templateId = job.workflow_template_id?.trim();
  if (!templateId) {return null;}

  const label = resolveTemplateLabel(job);
  const argsEntries = Object.entries(job.workflow_template_args ?? {}).filter(
    ([, value]) => value.trim().length > 0,
  );

  return (
    <div className="rounded-lg border border-border/60 bg-card/60 px-4 py-3 space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium text-foreground">{t('workflowTemplateDetailTitle')}</p>
          <p className="text-sm text-foreground break-all">{label}</p>
          {label !== templateId ? (
            <p className="text-[11px] text-muted-foreground break-all">{templateId}</p>
          ) : null}
          {argsEntries.length > 0 ? (
            <div className="space-y-1 pt-1">
              <p className="text-[11px] text-muted-foreground">{t('workflowTemplateArgsLabel')}</p>
              <ul className="space-y-0.5">
                {argsEntries.map(([key, value]) => (
                  <li key={key} className="text-xs text-muted-foreground break-all">
                    <span className="font-medium text-foreground/90">{key}</span>
                    <span className="mx-1">=</span>
                    <span>{value}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
        <Button asChild variant="outline" size="sm" className="shrink-0 self-start">
          <Link href={LIBRARY_HREF}>{t('workflowTemplateOpenLibrary')}</Link>
        </Button>
      </div>
    </div>
  );
}
