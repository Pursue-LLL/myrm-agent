'use client';

/**
 * 智能体侧边栏内容组件
 *
 * [INPUT]
 * - selectedId: 当前选中的智能体 ID
 * - onSelect: 选择智能体回调
 * - onToggleCollapse: 侧边栏折叠切换回调
 *
 * [OUTPUT]
 * - AgentSidebarContent: 智能体侧边栏内容组件
 *   - 智能体列表
 *   - 创建新智能体按钮
 *   - 删除确认对话框
 *
 * [POS]
 * 侧边栏智能体列表。显示搜索、创建按钮、智能体列表。
 * 支持使用、编辑、删除智能体。
 */

import { memo, useState, useCallback, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { Loader2, Trash2, Pencil, MessageSquare, Search, Bot } from 'lucide-react';
import BrandLogo from '@/components/ui/BrandLogo';
import { cn } from '@/lib/utils/classnameUtils';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import useAgentStore from '@/store/useAgentStore';
import useAuthStore from '@/store/useAuthStore';
import { useShallow } from 'zustand/react/shallow';
import { useToast } from '@/hooks/useToast';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { AgentListItem } from '@/services/agent';

export interface AgentSidebarContentProps {
  selectedId?: string;
  onSelect?: (id: string | undefined) => void;
  onToggleCollapse: () => void;
}

// 侧边栏折叠图标
const SidebarCollapseIcon = memo(() => (
  <svg width="20" height="20" fill="none" viewBox="0 0 20 20" className="text-muted-foreground">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M2.167 6.667A2.833 2.833 0 0 1 5 3.833h2.708v12.334H5a2.833 2.833 0 0 1-2.833-2.834V6.667ZM9.042 17.5H5a4.167 4.167 0 0 1-4.167-4.167V6.667A4.167 4.167 0 0 1 5 2.5h10a4.167 4.167 0 0 1 4.167 4.167v6.666A4.167 4.167 0 0 1 15 17.5H9.042Zm0-13.667H15a2.833 2.833 0 0 1 2.833 2.834v6.666A2.833 2.833 0 0 1 15 16.167H9.042V3.833ZM3.583 6.5c0-.368.336-.667.75-.667H5.75c.414 0 .75.299.75.667 0 .368-.336.667-.75.667H4.333c-.414 0-.75-.299-.75-.667Zm.75 1.833c-.414 0-.75.299-.75.667 0 .368.336.667.75.667H5.75c.414 0 .75-.299.75-.667 0-.368-.336-.667-.75-.667H4.333Z"
      fill="currentColor"
    />
  </svg>
));
SidebarCollapseIcon.displayName = 'SidebarCollapseIcon';

export const AgentSidebarContent = memo<AgentSidebarContentProps>(
  ({ selectedId, onSelect: _onSelect, onToggleCollapse }) => {
    const t = useTranslations();
    const locale = useLocale();
    const router = useRouter();
    const { toast } = useToast();
    const [searchValue, setSearchValue] = useState('');
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [agentToDelete, setAgentToDelete] = useState<AgentListItem | null>(null);

    const { user, isInitialized } = useAuthStore();
    const { agents, loading, fetchAgents, remove } = useAgentStore(
      useShallow((state) => ({
        agents: state.agents,
        loading: state.loading,
        fetchAgents: state.fetchAgents,
        remove: state.remove,
      })),
    );

    // 加载智能体列表
    useEffect(() => {
      if (isInitialized && user) {
        fetchAgents();
      }
    }, [isInitialized, user, fetchAgents]);

    // 过滤智能体（基于 i18n 名称搜索，支持本地化搜索）
    const filteredAgents = useMemo(() => {
      if (!searchValue.trim()) return agents;
      const query = searchValue.toLowerCase();
      return agents.filter((agent) => {
        const name = getBuiltinAgentName(agent.id, agent.name, locale);
        const desc = getBuiltinAgentDescription(agent.id, agent.description || '', locale);
        return name.toLowerCase().includes(query) || desc.toLowerCase().includes(query);
      });
    }, [agents, searchValue, locale]);

    const handleCreateNew = useCallback(() => {
      router.push('/settings/agents?action=create');
    }, [router]);

    const handleUseAgent = useCallback(
      (agent: AgentListItem) => {
        router.push(`/?agent_id=${agent.id}`);
      },
      [router],
    );

    const handleEditAgent = useCallback(
      (agent: AgentListItem) => {
        router.push(`/settings/agents?agentId=${agent.id}`);
      },
      [router],
    );

    const handleDeleteRequest = useCallback((agent: AgentListItem) => {
      setAgentToDelete(agent);
      setDeleteDialogOpen(true);
    }, []);

    const handleConfirmDelete = useCallback(async () => {
      if (!agentToDelete) return;
      const success = await remove(agentToDelete.id);
      if (success) {
        toast({ title: t('agent.deleteSuccess') });
      } else {
        toast({ title: t('agent.operationFailed'), variant: 'destructive' });
      }
      setDeleteDialogOpen(false);
      setAgentToDelete(null);
    }, [agentToDelete, remove, toast, t]);

    return (
      <div className="flex flex-col h-full">
        {/* Header: Logo + Collapse Button */}
        <div className="p-3 flex items-center justify-between flex-shrink-0">
          <button
            onClick={() => router.push('/')}
            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
            aria-label="Home"
          >
            <BrandLogo size={40} priority className="w-10 h-10" />
            <span className="text-lg font-semibold brand-gradient-text">MyrmAgent</span>
          </button>
          <button
            onClick={onToggleCollapse}
            className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-muted transition-colors text-muted-foreground"
            aria-label={t('common.collapseMenu')}
          >
            <SidebarCollapseIcon />
          </button>
        </div>

        {/* Divider */}
        <div className="mx-3 border-t border-border/50" />

        {/* Search */}
        <div className="p-3 flex-shrink-0">
          <div className="flex items-center gap-2 px-3 h-9 rounded-full bg-muted/50 border border-border/50 transition-all duration-200 focus-within:border-border">
            <Search size={14} className="shrink-0 text-muted-foreground/50" />
            <input
              type="text"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              placeholder={t('sidebar.searchAgents')}
              className="flex-1 text-sm bg-transparent border-none outline-none text-foreground placeholder:text-muted-foreground/50"
            />
          </div>
        </div>

        {/* Create Button */}
        <div className="px-3 pb-3 flex-shrink-0">
          <button
            onClick={handleCreateNew}
            className={cn(
              'w-full flex items-center gap-3 p-2 rounded-xl cursor-pointer text-sm brand-interactive-hover',
              'bg-background dark:bg-background',
              'border border-border/60 dark:border-border/60',
              'text-foreground dark:text-foreground',
              'transition-all duration-200',
            )}
          >
            <Bot size={20} className="text-current" />
            <span className="whitespace-nowrap">{t('agent.create')}</span>
          </button>
        </div>

        {/* Agent List */}
        <div className="flex-1 overflow-y-auto px-3 pb-3">
          {!isInitialized || loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : !user ? (
            <div className="text-sm text-muted-foreground py-4 text-center">{t('agent.empty')}</div>
          ) : filteredAgents.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4 text-center">
              {searchValue ? t('search.noResults') : t('agent.empty')}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredAgents.map((agent) => (
                <div
                  key={agent.id}
                  className={cn(
                    'group relative p-3 rounded-xl cursor-pointer',
                    'bg-muted/30 hover:bg-muted/50',
                    'border border-transparent hover:border-border/50',
                    'transition-all duration-200',
                    selectedId === agent.id && 'brand-selected-surface border-primary/30',
                  )}
                  onClick={() => handleUseAgent(agent)}
                >
                  <div className="flex items-start gap-3">
                    <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} size="md" />
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium text-foreground truncate">
                        {getBuiltinAgentName(agent.id, agent.name, locale)}
                      </h4>
                      {agent.description && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {getBuiltinAgentDescription(agent.id, agent.description, locale)}
                        </p>
                      )}
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <button
                          className={cn(
                            'opacity-0 group-hover:opacity-100',
                            'p-1.5 rounded-full hover:bg-background/80',
                            'transition-all duration-200',
                          )}
                        >
                          <svg
                            width="16"
                            height="16"
                            viewBox="0 0 16 16"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                          >
                            <path
                              d="M8 3.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm0 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm0 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"
                              fill="currentColor"
                            />
                          </svg>
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                        <DropdownMenuItem onClick={() => handleUseAgent(agent)}>
                          <MessageSquare className="w-4 h-4 mr-2" />
                          {t('agent.use')}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleEditAgent(agent)}>
                          <Pencil className="w-4 h-4 mr-2" />
                          {t('agent.edit')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => handleDeleteRequest(agent)}
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          {t('agent.delete')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Delete Dialog */}
        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('agent.confirmDelete')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('agent.confirmDeleteDesc', {
                  name: agentToDelete ? getBuiltinAgentName(agentToDelete.id, agentToDelete.name, locale) : '',
                })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmDelete}>{t('common.delete')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  },
);

AgentSidebarContent.displayName = 'AgentSidebarContent';

export default AgentSidebarContent;
