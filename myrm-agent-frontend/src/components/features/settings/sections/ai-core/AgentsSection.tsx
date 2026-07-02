'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { useRouter, useSearchParams } from 'next/navigation';
import Image from 'next/image';
import {
  IconArrowRight,
  IconChat,
  IconCopy,
  IconEdit,
  IconEye,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUpload,
} from '@/components/features/icons/PremiumIcons';
import { AiNetworkIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { AgentIcon } from '@/components/agent/agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { Button } from '@/components/primitives/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Input } from '@/components/primitives/input';
import useAuthStore from '@/store/useAuthStore';
import { toast } from '@/hooks/useToast';
import { AgentListItem, listAgents, deleteAgent, importAgent, AGENT_LIST_BUILTIN_PAGE_SIZE } from '@/services/agent';
import SettingsSection from '../SettingsSection';
import LoginPrompt from '@/components/features/app-shell/login-prompt';
import AgentEditPanel from './AgentEditPanel';
import { isLocalMode } from '@/lib/deploy-mode';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';
import { validateAgentDependencies } from '@/lib/utils/agentConfigValidator';
import CloneAgentDialog from './CloneAgentDialog';

// 预设头像颜色方案
const avatarGradients = [
  { from: 'from-primary', to: 'to-violet-500', label: 'Purple' },
  { from: 'from-blue-500', to: 'to-cyan-500', label: 'Ocean' },
  { from: 'from-emerald-500', to: 'to-teal-500', label: 'Forest' },
  { from: 'from-orange-500', to: 'to-amber-500', label: 'Sunset' },
  { from: 'from-pink-500', to: 'to-rose-500', label: 'Rose' },
  { from: 'from-indigo-500', to: 'to-purple-500', label: 'Galaxy' },
];

// 根据 avatar_url 解析颜色索引
const getGradientFromAvatarUrl = (avatarUrl?: string, fallbackIndex: number = 0) => {
  if (avatarUrl?.startsWith('gradient:')) {
    const gradientIndex = parseInt(avatarUrl.replace('gradient:', ''), 10);
    if (!isNaN(gradientIndex) && gradientIndex >= 0 && gradientIndex < avatarGradients.length) {
      return avatarGradients[gradientIndex];
    }
  }
  return avatarGradients[fallbackIndex % avatarGradients.length];
};

export default function AgentsSection() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isInitialized } = useAuthStore();
  const isLocal = isLocalMode();

  // 从 URL 参数读取 agentId 和 new 标记
  const agentId = searchParams.get('agentId');
  const isNewAgent = searchParams.get('new') === 'true';

  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<AgentListItem | null>(null);
  const [cloneDialogOpen, setCloneDialogOpen] = useState(false);
  const [agentToClone, setAgentToClone] = useState<AgentListItem | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const { marketSkills, localSkills } = useSkillStore();
  const { mcpConfigs } = useConfigStore();
  const skills = useMemo(() => [...marketSkills, ...localSkills], [marketSkills, localSkills]);

  // 过滤后的智能体列表
  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) return agents;
    const query = searchQuery.toLowerCase();
    return agents.filter((agent) => {
      const name = getBuiltinAgentName(agent.id, agent.name, locale);
      const desc = getBuiltinAgentDescription(agent.id, agent.description || '', locale);
      return name.toLowerCase().includes(query) || desc.toLowerCase().includes(query);
    });
  }, [agents, searchQuery, locale]);

  // 加载智能体列表
  const loadAgentList = useCallback(async () => {
    if (!isLocal && !user) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const data = await listAgents(1, AGENT_LIST_BUILTIN_PAGE_SIZE);
      setAgents(data.items || []);
    } catch {
      toast({
        title: t('agent.operationFailed'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [user, t]);

  useEffect(() => {
    if (isInitialized && !agentId && !isNewAgent) {
      loadAgentList();
    }
  }, [isInitialized, loadAgentList, agentId, isNewAgent]);

  // 处理创建智能体 - 直接跳转到编辑页面，在保存时才调用后端 API
  const handleCreateAgent = useCallback(() => {
    // 使用 new=true 参数表示这是新建智能体
    router.push('/settings/agents?new=true');
  }, [router]);

  // 处理导入智能体
  const handleImportAgent = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const agentData = JSON.parse(text);

        // 调用导入 API
        const importedAgent = await importAgent(agentData);

        // 检查依赖缺失
        const validation = validateAgentDependencies(importedAgent, skills, mcpConfigs);

        if (!validation.isValid) {
          const missingParts = [];
          if (validation.missingSkills.length > 0) missingParts.push(`${validation.missingSkills.length} 个技能`);
          if (validation.missingMcps.length > 0) missingParts.push(`${validation.missingMcps.length} 个 MCP 服务`);

          toast({
            title: '导入成功，但存在依赖缺失',
            description: `已成功导入智能体，但当前系统缺少该智能体依赖的 ${missingParts.join('和')}。请在编辑页面检查并重新配置。`,
            variant: 'default',
            duration: 8000,
          });
        } else {
          toast({ title: '导入成功', description: `已成功导入智能体配置` });
        }

        // 重新加载列表
        loadAgentList();
      } catch (e) {
        console.error('Import failed:', e);
        toast({
          title: '导入失败',
          description: '文件格式不正确或配置无效',
          variant: 'destructive',
        });
      } finally {
        // 清空 input，允许重复选择同一个文件
        event.target.value = '';
      }
    },
    [loadAgentList, skills, mcpConfigs],
  );

  // 处理删除智能体
  const handleDeleteAgent = useCallback(async () => {
    if (!agentToDelete) return;

    try {
      await deleteAgent(agentToDelete.id);
      setAgents((prev) => prev.filter((a) => a.id !== agentToDelete.id));
      toast({ title: t('agent.deleteSuccess') });
    } catch {
      toast({
        title: t('agent.operationFailed'),
        variant: 'destructive',
      });
    } finally {
      setDeleteDialogOpen(false);
      setAgentToDelete(null);
    }
  }, [agentToDelete, t]);

  const openCloneDialog = useCallback((agent: AgentListItem) => {
    setAgentToClone(agent);
    setCloneDialogOpen(true);
  }, []);

  const handleSelectAgent = useCallback(
    (agent: AgentListItem) => {
      router.push(`/?agent_id=${agent.id}`);
    },
    [router],
  );

  // 处理编辑智能体
  const handleEditAgent = useCallback(
    (agent: AgentListItem) => {
      router.push(`/settings/agents?agentId=${agent.id}`);
    },
    [router],
  );

  // 从编辑视图返回列表
  const handleBackToList = useCallback(() => {
    router.push('/settings/agents');
    // 重新加载列表以获取最新数据
    loadAgentList();
  }, [router, loadAgentList]);

  // 如果有 agentId 或 isNewAgent，显示编辑面板
  if (agentId || isNewAgent) {
    return <AgentEditPanel agentId={agentId} isNew={isNewAgent} onBack={handleBackToList} />;
  }

  if (!isLocal && isInitialized && !user) {
    return (
      <SettingsSection title={t('agent.title')} description={t('agent.description')}>
        <LoginPrompt title={t('settings.skills.loginRequired')} description={t('settings.skills.loginRequiredDesc')} />
      </SettingsSection>
    );
  }

  // 加载中
  if (loading) {
    return (
      <SettingsSection title={t('agent.title')} description={t('agent.description')}>
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/20 blur-xl animate-pulse" />
            <div className="relative animate-spin rounded-full h-12 w-12 border-2 border-primary/20 border-t-primary" />
          </div>
        </div>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection title={t('agent.title')} description={t('agent.description')}>
      <div className="space-y-6">
        {/* 头部：搜索 + 创建按钮 */}
        <div className="flex items-center gap-3">
          {agents.length > 0 && (
            <div className="relative flex-1">
              <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder={t('agent.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-muted/50"
              />
            </div>
          )}
          <div className="flex items-center gap-2 flex-shrink-0">
            <label>
              <input type="file" accept=".json,.agent.json" className="hidden" onChange={handleImportAgent} />
              <Button variant="outline" className="gap-2 cursor-pointer" asChild>
                <span>
                  <IconUpload className="w-[18px] h-[18px]" />
                  <span className="hidden sm:inline">导入</span>
                </span>
              </Button>
            </label>
            <Button onClick={handleCreateAgent} className="gap-2">
              <IconPlus className="w-[18px] h-[18px]" />
              <span className="hidden sm:inline">{t('agent.create')}</span>
            </Button>
          </div>
        </div>

        {/* 智能体列表 */}
        {agents.length === 0 ? (
          /* 空状态 */
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent rounded-3xl" />
            <div className="relative flex flex-col items-center justify-center py-16 px-4 text-center">
              <div className="relative mb-6">
                <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-violet-500/20 blur-3xl" />
                <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-muted to-muted/50 border border-border flex items-center justify-center">
                  <AiNetworkIcon size={36} className="text-muted-foreground/60" />
                </div>
              </div>
              <h3 className="text-xl font-semibold text-foreground mb-2">{t('agent.empty')}</h3>
              <p className="text-muted-foreground mb-6 max-w-md">{t('agent.emptyDesc')}</p>
              <Button onClick={handleCreateAgent} className="gap-2">
                <IconPlus className="w-[18px] h-[18px]" />
                {t('agent.create')}
              </Button>
            </div>
          </div>
        ) : filteredAgents.length === 0 ? (
          /* 搜索无结果 */
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <IconSearch className="w-10 h-10 text-muted-foreground/40 mb-4" />
            <p className="text-muted-foreground">{t('search.noResults')}</p>
          </div>
        ) : (
          /* 智能体卡片网格 */
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredAgents.map((agent, index) => (
              <div
                key={agent.id}
                className={cn(
                  'group relative rounded-xl overflow-hidden',
                  'bg-card border border-border/50',
                  'hover:border-primary/30 hover:shadow-lg hover:shadow-primary/10',
                  'transition-all duration-300 cursor-pointer',
                )}
                onClick={() => handleSelectAgent(agent)}
              >
                {/* 卡片内容 */}
                <div className="relative p-4">
                  {/* 头像和操作 */}
                  <div className="flex items-start justify-between mb-3">
                    {(() => {
                      const gradient = getGradientFromAvatarUrl(agent.avatar_url, index);
                      const parsed = parseAvatarUrl(agent.avatar_url, agent.id);

                      if (parsed?.type === 'icon') {
                        return <AgentIcon iconId={parsed.iconId} size="md" className="w-10 h-10" />;
                      }

                      return (
                        <div
                          className={cn(
                            'w-10 h-10 rounded-lg flex items-center justify-center',
                            parsed?.type === 'image' && 'relative overflow-hidden',
                            parsed?.type !== 'emoji' && 'bg-gradient-to-br',
                            parsed?.type !== 'emoji' && gradient.from,
                            parsed?.type !== 'emoji' && gradient.to,
                          )}
                        >
                          {parsed?.type === 'emoji' ? (
                            <span className="text-2xl">{parsed.emoji}</span>
                          ) : parsed?.type === 'image' ? (
                            <Image
                              src={parsed.src}
                              alt={agent.name}
                              fill
                              sizes="40px"
                              unoptimized={parsed.src.startsWith('http://') || parsed.src.startsWith('https://')}
                              className="object-cover"
                            />
                          ) : (
                            <AiNetworkIcon size={22} className="text-white" />
                          )}
                        </div>
                      );
                    })()}

                    {/* 操作按钮 */}
                    <div
                      className={cn(
                        'flex items-center gap-1',
                        'opacity-0 group-hover:opacity-100 transition-opacity duration-200',
                      )}
                    >
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEditAgent(agent);
                        }}
                        className={cn(
                          'p-2 rounded-lg',
                          'bg-background/80 hover:bg-background',
                          'border border-border/50 hover:border-border',
                          'transition-all duration-200',
                        )}
                        title={agent.is_built_in ? t('agent.view') : t('agent.edit')}
                      >
                        {agent.is_built_in ? (
                          <IconEye className="w-3.5 h-3.5 text-muted-foreground" />
                        ) : (
                          <IconEdit className="w-3.5 h-3.5 text-muted-foreground" />
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openCloneDialog(agent);
                        }}
                        className={cn(
                          'p-2 rounded-lg',
                          'bg-background/80 hover:bg-background',
                          'border border-border/50 hover:border-border',
                          'transition-all duration-200',
                        )}
                        title={t('agent.clone')}
                      >
                        <IconCopy className="w-3.5 h-3.5 text-muted-foreground" />
                      </button>
                      {!agent.is_built_in && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setAgentToDelete(agent);
                            setDeleteDialogOpen(true);
                          }}
                          className={cn(
                            'p-2 rounded-lg',
                            'bg-background/80 hover:bg-destructive/10',
                            'border border-border/50 hover:border-destructive/30',
                            'transition-all duration-200',
                          )}
                          title={t('agent.delete')}
                        >
                          <IconTrash className="w-3.5 h-3.5 text-destructive" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* 名称和描述 */}
                  <div className="space-y-1.5 mb-4">
                    <h3 className="text-sm font-semibold text-foreground truncate">
                      {getBuiltinAgentName(agent.id, agent.name, locale)}
                    </h3>
                    <p className="text-xs text-muted-foreground line-clamp-2 min-h-[2rem]">
                      {getBuiltinAgentDescription(agent.id, agent.description || '', locale) ||
                        t('agent.noDescription')}
                    </p>
                  </div>

                  {/* 底部操作提示 */}
                  <div
                    className={cn(
                      'flex items-center justify-between pt-3 border-t border-border/30',
                      'group-hover:border-primary/20 transition-colors duration-300',
                    )}
                  >
                    <div
                      className={cn(
                        'flex items-center gap-1.5 text-xs',
                        'text-muted-foreground group-hover:text-primary',
                        'transition-colors duration-300',
                      )}
                    >
                      <IconChat className="w-3 h-3 group-hover:animate-pulse" />
                      <span>{t('agent.startChat')}</span>
                    </div>
                    <IconArrowRight
                      className={cn(
                        'w-3 h-3',
                        'text-muted-foreground/40',
                        'group-hover:text-primary group-hover:translate-x-1',
                        'transition-all duration-300',
                      )}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 删除确认对话框 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="rounded-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('agent.confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('agent.confirmDeleteDesc', {
                name: agentToDelete ? getBuiltinAgentName(agentToDelete.id, agentToDelete.name, locale) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-xl">{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteAgent}
              className="rounded-xl bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <CloneAgentDialog
        open={cloneDialogOpen}
        onOpenChange={setCloneDialogOpen}
        agentId={agentToClone?.id ?? null}
        agentName={agentToClone ? getBuiltinAgentName(agentToClone.id, agentToClone.name, locale) : null}
        onCloned={(cloned) => router.push(`/settings/agents?agentId=${cloned.id}`)}
      />
    </SettingsSection>
  );
}
