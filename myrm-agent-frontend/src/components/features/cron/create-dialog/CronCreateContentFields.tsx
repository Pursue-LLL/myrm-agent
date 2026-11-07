'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态与选项), ../cron-utils::PILL_TOGGLE_CLASS (POS: 胶囊切换样式), ./cronCreateModel (POS: 任务类型与哨兵值)
 * [OUTPUT] CronCreateContentFields: 任务类型、名称，以及随类型切换的内容输入（Agent / 提醒提示词 + 工作流模板、Shell 命令、Python 脚本）
 * [POS] 自定义创建流程的“跑什么”区块：Shell 类型仅在部署允许时可选，工作流模板只属于 Agent 类型，换模板会清空已填的模板参数。
 */

import { useTranslations } from 'next-intl';
import { Bot, CalendarDays, FileCode2, Terminal } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Textarea } from '@/components/primitives/textarea';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import { PILL_TOGGLE_CLASS } from '../cron-utils';
import { NO_WORKFLOW_TEMPLATE, type UIJobMode } from './cronCreateModel';
import type { CronCreateForm } from './useCronCreateForm';

export function CronCreateContentFields({ form }: { form: CronCreateForm }) {
  const t = useTranslations('cron');
  const { draft, patch, options } = form;
  const { uiMode, name, prompt, command, scriptCode, workflowTemplateId } = draft;

  return (
    <>
      {/* Job Type */}
      <div className="space-y-1.5">
        <Label className="text-xs">{t('createTypeLabel')}</Label>
        <ToggleGroup
          type="single"
          value={uiMode}
          onValueChange={(v) => v && patch({ uiMode: v as UIJobMode })}
          className="justify-start"
        >
          <ToggleGroupItem value="agent" className={PILL_TOGGLE_CLASS}>
            <Bot className="h-3.5 w-3.5" />
            {t('jobTypeAgent')}
          </ToggleGroupItem>
          {options.shellEnabled === true && (
            <ToggleGroupItem value="shell" className={PILL_TOGGLE_CLASS}>
              <Terminal className="h-3.5 w-3.5" />
              {t('jobTypeShell')}
            </ToggleGroupItem>
          )}
          <ToggleGroupItem value="script" className={PILL_TOGGLE_CLASS}>
            <FileCode2 className="h-3.5 w-3.5" />
            {t('jobTypeScript')}
          </ToggleGroupItem>
          <ToggleGroupItem value="reminder" className={PILL_TOGGLE_CLASS}>
            <CalendarDays className="h-3.5 w-3.5" />
            {t('jobTypeReminder')}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Name */}
      <div className="space-y-1.5">
        <Label className="text-xs">{t('createNameLabel')}</Label>
        <Input
          placeholder={t('createNamePlaceholder')}
          value={name}
          onChange={(e) => patch({ name: e.target.value })}
          className="h-8 text-sm"
        />
      </div>

      {/* Content: Agent prompt */}
      {(uiMode === 'agent' || uiMode === 'reminder') && (
        <div className="space-y-1.5">
          <Label className="text-xs">{uiMode === 'reminder' ? t('createReminderLabel') : t('createPromptLabel')}</Label>
          <Textarea
            placeholder={uiMode === 'reminder' ? t('createReminderPlaceholder') : t('createPromptPlaceholder')}
            value={prompt}
            onChange={(e) => patch({ prompt: e.target.value })}
            className="min-h-[80px] text-sm resize-none"
          />
          {uiMode === 'reminder' ? (
            <p className="text-[11px] text-muted-foreground">{t('createReminderHint')}</p>
          ) : null}
          {uiMode === 'agent' ? (
            <div className="space-y-1.5 pt-1">
              <Label className="text-xs">{t('createWorkflowTemplateLabel')}</Label>
              <Select
                value={workflowTemplateId}
                onValueChange={(value) => patch({ workflowTemplateId: value, workflowTemplateArgs: null })}
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_WORKFLOW_TEMPLATE}>{t('createWorkflowTemplateNone')}</SelectItem>
                  {options.workflowTemplates.map((template) => (
                    <SelectItem key={template.template_id} value={template.template_id}>
                      {template.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">{t('createWorkflowTemplateHint')}</p>
            </div>
          ) : null}
        </div>
      )}

      {/* Content: Shell command */}
      {uiMode === 'shell' && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('createCommandLabel')}</Label>
          <Input
            placeholder={t('createCommandPlaceholder')}
            value={command}
            onChange={(e) => patch({ command: e.target.value })}
            className="h-8 text-sm font-mono"
          />
        </div>
      )}

      {/* Content: Python script */}
      {uiMode === 'script' && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('scriptLabel')}</Label>
          <Textarea
            placeholder={t('scriptPlaceholder')}
            value={scriptCode}
            onChange={(e) => patch({ scriptCode: e.target.value })}
            className="min-h-[100px] text-sm resize-none font-mono"
          />
          <p className="text-[11px] text-muted-foreground">{t('scriptHint')}</p>
        </div>
      )}
    </>
  );
}
