'use client';

/**
 * [INPUT] @/store/useAgentStore, @/store/useProjectStore
 * [OUTPUT] ProjectDefaultAgentDialog: 项目默认智能体选择弹窗
 * [POS] 供 ProjectBar 右键菜单调用，展示可选智能体列表并绑定到项目。
 */

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Check, Loader2, X } from 'lucide-react';
import { useToast } from '@/hooks/shared/useToast';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { cn } from '@/lib/utils/classnameUtils';
import useAgentStore from '@/store/useAgentStore';
import { useProjectStore } from '@/store/useProjectStore';
import type { Project } from '@/services/projects';

interface ProjectDefaultAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
}

export function ProjectDefaultAgentDialog({ open, onOpenChange, project }: ProjectDefaultAgentDialogProps) {
  const t = useTranslations();
  const locale = useLocale();
  const { toast } = useToast();
  const { agents, fetchAgents, loading: agentsLoading } = useAgentStore();
  const { updateProject } = useProjectStore();
  const [selectedId, setSelectedId] = useState<string | null>(project.defaultAgentId ?? null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setSelectedId(project.defaultAgentId ?? null);
      fetchAgents(1, 50, true);
    }
  }, [open, project.defaultAgentId, fetchAgents]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateProject(project.id, { default_agent_id: selectedId });
      onOpenChange(false);
    } catch (err) {
      toast({
        title: t('project.defaultAgent.saveFailed'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const hasChanged = selectedId !== (project.defaultAgentId ?? null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle className="text-sm">{t('project.defaultAgent.title')}</DialogTitle>
          <DialogDescription className="text-xs">{t('project.defaultAgent.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1 max-h-[320px] overflow-y-auto py-2">
          {agentsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={18} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* "None" option to clear binding */}
              <button
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors text-left',
                  selectedId === null ? 'bg-accent text-accent-foreground' : 'hover:bg-black/5 dark:hover:bg-white/5',
                )}
                onClick={() => setSelectedId(null)}
              >
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted">
                  <X size={14} className="text-muted-foreground" />
                </div>
                <span className="text-muted-foreground">{t('project.defaultAgent.none')}</span>
                {selectedId === null && <Check size={14} className="ml-auto shrink-0" />}
              </button>

              {agents.map((agent) => (
                <button
                  key={agent.id}
                  className={cn(
                    'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors text-left',
                    selectedId === agent.id
                      ? 'bg-accent text-accent-foreground'
                      : 'hover:bg-black/5 dark:hover:bg-white/5',
                  )}
                  onClick={() => setSelectedId(agent.id)}
                >
                  <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} className="h-7 w-7" />
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="truncate text-sm font-medium">
                      {getBuiltinAgentName(agent.id, agent.name, locale)}
                    </span>
                    {agent.description && (
                      <span className="truncate text-[10px] text-muted-foreground">{agent.description}</span>
                    )}
                  </div>
                  {selectedId === agent.id && <Check size={14} className="ml-auto shrink-0" />}
                </button>
              ))}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!hasChanged || saving}>
            {saving && <Loader2 size={14} className="animate-spin mr-1" />}
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
