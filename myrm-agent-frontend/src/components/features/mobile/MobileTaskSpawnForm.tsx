'use client';

/**
 * [INPUT]
 * - agents: SpawnOptionAgent[]
 * - projects: SpawnOptionProject[]
 * - slotsFull: boolean
 * - submitting: boolean
 * - onSubmit: (agentId: string, projectId: string, message: string) => Promise<void>
 *
 * [OUTPUT]
 * - MobileTaskSpawnForm: Extracted collapsible mobile task spawn form component
 *
 * [POS]
 * Decomposed subcomponent of MobileSessionHub to maintain strict < 400 lines limit.
 */

import { useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { IconChevronUp, IconPlus } from '@/components/features/icons/PremiumIcons';
import { isImeComposing } from '@/lib/utils/imeUtils';
import type { SpawnOptionAgent, SpawnOptionProject } from '@/services/remoteAccess';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

export interface MobileTaskSpawnFormProps {
  agents: SpawnOptionAgent[];
  projects: SpawnOptionProject[];
  slotsFull: boolean;
  submitting: boolean;
  selectedAgentId: string;
  onSelectAgent: (id: string) => void;
  selectedProjectId: string;
  onSelectProject: (id: string) => void;
  taskMessage: string;
  onTaskMessageChange: (msg: string) => void;
  onSubmit: () => Promise<void>;
  onOpenOptions: () => void;
}

export function MobileTaskSpawnForm({
  agents,
  projects,
  slotsFull,
  submitting,
  selectedAgentId,
  onSelectAgent,
  selectedProjectId,
  onSelectProject,
  taskMessage,
  onTaskMessageChange,
  onSubmit,
  onOpenOptions,
}: MobileTaskSpawnFormProps) {
  const t = useTranslations('mobileHub');
  const locale = useLocale();
  const [formOpen, setFormOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleToggle = () => {
    const next = !formOpen;
    setFormOpen(next);
    if (next) {
      onOpenOptions();
    }
  };

  return (
    <section className="rounded-2xl border bg-card p-4 shadow-xs">
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={formOpen}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <IconPlus className="h-4 w-4 text-primary" />
          <span>{formOpen ? t('newTaskCollapse') : t('newTask')}</span>
        </span>
        <IconChevronUp
          className={`h-4 w-4 text-muted-foreground transition-transform ${
            formOpen ? '' : 'rotate-180'
          }`}
        />
      </button>

      {formOpen && (
        <div className="mt-4 space-y-3 pt-3 border-t">
          {slotsFull && (
            <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-relaxed text-destructive">
              {t('slotsFull')}
            </p>
          )}
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">{t('selectAgent')}</span>
            <select
              value={selectedAgentId}
              onChange={(e) => onSelectAgent(e.target.value)}
              aria-label={t('selectAgent')}
              className="block w-full rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {getBuiltinAgentName(a.id, a.name, locale)}
                </option>
              ))}
            </select>
          </label>

          {projects.length > 0 && (
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">{t('selectProject')}</span>
              <select
                value={selectedProjectId}
                onChange={(e) => onSelectProject(e.target.value)}
                aria-label={t('selectProject')}
                className="block w-full rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
              >
                <option value="">{t('noProject')}</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">{t('taskDescription')}</span>
            <textarea
              ref={textareaRef}
              value={taskMessage}
              onChange={(e) => onTaskMessageChange(e.target.value)}
              onKeyDown={(e) => {
                if (isImeComposing(e)) {
                  return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void onSubmit();
                }
              }}
              placeholder={t('taskPlaceholder')}
              rows={3}
              className="block w-full resize-none rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
            />
          </label>

          <button
            type="button"
            onClick={() => void onSubmit()}
            disabled={submitting || !taskMessage.trim() || !selectedAgentId || slotsFull}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? t('submitting') : t('submit')}
          </button>
        </div>
      )}
    </section>
  );
}
