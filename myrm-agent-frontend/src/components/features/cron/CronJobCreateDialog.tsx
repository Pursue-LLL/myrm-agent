'use client';

/**
 * [INPUT] ./create-dialog/{useCronCreateForm, CronCreateCustomForm} (POS: 草稿状态与 Custom 表单), ./BlueprintCatalog + ./BlueprintInlineFill (POS: 模板创建流程), ./CronJobAuditPanel (POS: 创建后审计), @/lib/cron/cronCreateAuditGate::canDismissSettingsAuditFlow (POS: 审计门禁), WorkflowTemplateArgsDialog (POS: 工作流模板参数)
 * [OUTPUT] CronJobCreateDialog (default): 创建定时任务弹窗——Template / Custom 两个页签，创建成功后切到审计面板
 * [POS] 弹窗外壳：只管页签、模板流程与创建后审计；Custom 表单与全部状态在 ./create-dialog。关闭（含取消、审计完成）统一重置全部草稿。
 */

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { CronJob } from '@/services/cron.types';
import { canDismissSettingsAuditFlow } from '@/lib/cron/cronCreateAuditGate';
import WorkflowTemplateArgsDialog from '@/components/features/settings/sections/ai-tools/WorkflowTemplateArgsDialog';
import BlueprintCatalog from './BlueprintCatalog';
import BlueprintInlineFill from './BlueprintInlineFill';
import { CronJobAuditPanel } from './CronJobAuditPanel';
import { CronCreateCustomForm } from './create-dialog/CronCreateCustomForm';
import { useCronCreateForm } from './create-dialog/useCronCreateForm';

interface ModeTabProps {
  active: boolean;
  testId: string;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}

function ModeTab({ active, testId, onClick, className, children }: ModeTabProps) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 text-xs font-medium border-b-2 -mb-px transition-colors',
        className,
        active ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}

interface CreatedJobPanelProps {
  job: CronJob;
  onJobChange: (job: CronJob) => void;
  onDone: () => void;
}

function CreatedJobPanel({ job, onJobChange, onDone }: CreatedJobPanelProps) {
  const t = useTranslations('cron');
  const canDismiss = canDismissSettingsAuditFlow(job);

  return (
    <div className="space-y-4 pt-2">
      <CronJobAuditPanel jobId={job.id} initialJob={job} enforceSettingsGate onJobChange={onJobChange} />
      <div className="flex justify-end gap-2 pt-2">
        <Button size="sm" disabled={!canDismiss} title={canDismiss ? undefined : t('auditDoneHint')} onClick={onDone}>
          {t('auditDone')}
        </Button>
      </div>
    </div>
  );
}

interface CronJobCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  presetChatId?: string | null;
  presetChatTitle?: string | null;
}

export default function CronJobCreateDialog({
  open,
  onOpenChange,
  presetChatId,
  presetChatTitle,
}: CronJobCreateDialogProps) {
  const t = useTranslations('cron');
  const form = useCronCreateForm({ open, presetChatId });
  const { draft, patch, reset, selectedWorkflowTemplate } = form;
  const { createdJob, createMode, selectedBlueprint } = draft;

  const close = () => {
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          reset();
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            {t('createTitle')}
          </DialogTitle>
        </DialogHeader>

        {createdJob ? (
          <CreatedJobPanel job={createdJob} onJobChange={(job) => patch({ createdJob: job })} onDone={close} />
        ) : (
          <div className="space-y-4 pt-2">
            {/* Mode Toggle */}
            <div className="flex gap-1 border-b pb-0">
              <ModeTab
                active={createMode === 'template'}
                testId="cron-create-mode-template"
                onClick={() => patch({ createMode: 'template' })}
                className="flex items-center gap-1"
              >
                <Sparkles className="h-3 w-3" />
                {t('blueprint.tabTemplate')}
              </ModeTab>
              <ModeTab
                active={createMode === 'custom'}
                testId="cron-create-mode-custom"
                onClick={() => patch({ createMode: 'custom' })}
              >
                {t('blueprint.tabCustom')}
              </ModeTab>
            </div>

            {/* Template Mode */}
            {createMode === 'template' && !selectedBlueprint && (
              <BlueprintCatalog onSelect={(blueprint) => patch({ selectedBlueprint: blueprint })} />
            )}

            {/* Template Fill View (inline) */}
            {createMode === 'template' && selectedBlueprint && (
              <BlueprintInlineFill
                blueprint={selectedBlueprint}
                onBack={() => patch({ selectedBlueprint: null })}
                onCreated={(job) => patch({ createdJob: job })}
              />
            )}

            {/* Custom Mode */}
            {createMode === 'custom' && (
              <CronCreateCustomForm
                form={form}
                presetChatId={presetChatId}
                presetChatTitle={presetChatTitle}
                onCancel={close}
              />
            )}
          </div>
        )}
      </DialogContent>
      {selectedWorkflowTemplate ? (
        <WorkflowTemplateArgsDialog
          open={draft.workflowArgsDialogOpen}
          templateName={selectedWorkflowTemplate.display_name}
          placeholders={selectedWorkflowTemplate.placeholders}
          onOpenChange={(value) => patch({ workflowArgsDialogOpen: value })}
          onConfirm={form.confirmWorkflowArgs}
        />
      ) : null}
    </Dialog>
  );
}
