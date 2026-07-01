'use client';

import { memo, lazy, Suspense, useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Save, Zap } from 'lucide-react';
import AgentConfigCards from './AgentConfigCards';
import TypewriterWelcome from './TypewriterWelcome';
import { useAgentConfigPanel } from '@/hooks/useAgentConfigPanel';
import { useTranslations } from 'next-intl';
import { AiNetworkIcon } from 'hugeicons-react';
import { getConfigSyncManager, type ExternalAgentConfig } from '@/services/config';
import useChatStore from '@/store/useChatStore';
import { IconBrain } from '@/components/features/icons/PremiumIcons';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';

// 懒加载大型组件，减少初始加载时间
const AgentConfigEditDialog = lazy(() => import('./AgentConfigEditDialog'));
const PresetAgentGallery = lazy(() => import('./PresetAgentGallery'));
const EMPTY_AUTO_RESTORE_DOMAINS: string[] = [];

interface AgentConfigPanelProps {
  className?: string;
  /** 隐藏已保存智能体画廊（在有消息的聊天页面中使用） */
  hideGallery?: boolean;
}

/**
 * 智能体配置面板主容器
 * 仅在智能代理模式下显示
 * 包含：编辑面板（四个配置卡片）+ 橱窗面板（已保存智能体画廊）
 */
const AgentConfigPanel = ({ className, hideGallery = false }: AgentConfigPanelProps) => {
  // 使用自定义 Hook 获取所有状态和处理器
  const {
    // State
    isSavingAgent,
    editDialogOpen,
    editDialogType,
    showTypewriter,
    hasConfigChanges,

    // Config
    agentConfig,
    actionMode,
    isConfigPanelExpanded,

    // Data
    enabledSkills,
    enabledMcps,
    selectedSkillDetails,
    selectedMcpDetails,
    currentBuiltinTools,

    // Preset
    selectedPresetId,

    // Handlers
    setEditDialogOpen,
    handleCardClick,
    handleSaveConfig,
    handleSaveAsNewAgent,
    handleUpdateAgent,
    handleSelectAgent,
    handleSelectPreset,
    clearPresetSelection,
    handleTypewriterComplete,

    refreshSkills,

    // Translations
    t,
    tIndicator,
  } = useAgentConfigPanel();

  // 仅在智能代理模式下显示
  if (actionMode !== 'agent') {
    return null;
  }

  return (
    <div className={cn('w-full space-y-6', className)}>
      {/* 编辑面板区域 - 根据展开状态显示/隐藏 */}
      {isConfigPanelExpanded && (
        <div
          className={cn('relative py-4 px-2 overflow-hidden', 'animate-in fade-in-50 slide-in-from-top-2 duration-300')}
        >
          {/* 不规则气泡背景 - 泼墨效果，#fefef8 暖色系 */}
          <div
            className="absolute pointer-events-none"
            style={{
              inset: '-40px -60px -30px -60px',
              zIndex: 0,
            }}
          >
            {/* 主背景气泡 - SVG 实现不规则形状 */}
            <svg
              className="w-full h-full"
              viewBox="0 0 500 300"
              preserveAspectRatio="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <defs>
                {/* #fefef8 暖色系渐变 - 米黄/奶油色调 */}
                <linearGradient id="inkGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#fefef8" stopOpacity="0.6" />
                  <stop offset="30%" stopColor="#fdf9e6" stopOpacity="0.7" />
                  <stop offset="60%" stopColor="#fefcf3" stopOpacity="0.65" />
                  <stop offset="100%" stopColor="#fefef8" stopOpacity="0.5" />
                </linearGradient>
                {/* 更柔和的模糊效果 */}
                <filter id="inkBlur" x="-30%" y="-30%" width="160%" height="160%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="15" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* 主泼墨形状 - 更不规则，更大 */}
              <path
                d="M40,50 
                   C90,15 150,25 200,20
                   C280,12 350,30 420,25
                   C470,22 495,55 485,100
                   C490,140 480,190 460,230
                   C430,265 360,280 280,275
                   C200,278 120,270 60,255
                   C20,240 5,200 10,150
                   C8,100 15,70 40,50 Z"
                fill="url(#inkGradient)"
                filter="url(#inkBlur)"
              />

              {/* 溢出的小墨滴 - #fefef8 暖色系 */}
              <ellipse cx="470" cy="60" rx="25" ry="18" fill="#fdf9e6" fillOpacity="0.5" />
              <ellipse cx="30" cy="220" rx="22" ry="15" fill="#fefcf3" fillOpacity="0.5" />
              <circle cx="485" cy="180" r="18" fill="#fefef8" fillOpacity="0.45" />
              <circle cx="15" cy="80" r="20" fill="#fdf9e6" fillOpacity="0.48" />

              {/* 飞溅的小点 */}
              <circle cx="495" cy="120" r="8" fill="#fefcf3" fillOpacity="0.5" />
              <circle cx="5" cy="150" r="6" fill="#fefef8" fillOpacity="0.5" />
              <circle cx="460" cy="260" r="10" fill="#fdf9e6" fillOpacity="0.45" />
              <circle cx="40" cy="35" r="7" fill="#fefcf3" fillOpacity="0.48" />
            </svg>
          </div>

          {/* 指向智能体按钮的箭头 - 在气泡外面 */}
          <div
            className="absolute -top-8 left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-none"
            style={{ zIndex: 1 }}
          >
            {/* 渐变连接线 - 调整为暖色系 */}
            <div className="w-[2px] h-5 bg-gradient-to-b from-amber-300/50 via-amber-400/40 to-amber-200/20 rounded-full" />
            {/* 箭头尖端 */}
            <div className="w-3 h-3 rotate-45 bg-gradient-to-br from-amber-100/40 to-amber-200/30 border-l-2 border-t-2 border-amber-300/40 rounded-tl-sm -mt-1.5" />
          </div>

          {/* 打字机欢迎消息 - 在配置卡片上方 */}
          <div className="relative z-10">
            <TypewriterWelcome
              text={tIndicator('welcomeMessage')}
              show={showTypewriter}
              onComplete={handleTypewriterComplete}
              typingSpeed={35}
              displayDuration={1200}
            />
          </div>

          {/* 四个配置卡片 */}
          <div className="relative z-10">
            <AgentConfigCards
              selectedSkills={selectedSkillDetails}
              selectedMcps={selectedMcpDetails}
              systemPrompt={agentConfig?.systemPrompt || ''}
              useGlobalInstruction={agentConfig?.useGlobalInstruction ?? true}
              enabledBuiltinTools={currentBuiltinTools}
              ephemeralSubagents={agentConfig?.ephemeralSubagents}
              onCardClick={handleCardClick}
            />

            {/* 直连外部 Agent 选择器 */}
            <DirectDelegateSelector />

            {/* 场景化蓝图团队选择器 (JIT 一键编队) */}
            <ScenarioBlueprintSelector />

            {/* 记忆遗忘速度配置 (Advanced Settings) */}
            <MemoryDecaySelector />

            {/* 保存按钮逻辑 */}
            {(() => {
              const hasConfig =
                (agentConfig?.selectedSkillIds?.length || 0) > 0 ||
                (agentConfig?.selectedMcpNames?.length || 0) > 0 ||
                (agentConfig?.systemPrompt?.trim().length || 0) > 0;

              // 如果没有任何配置，不显示按钮
              if (!hasConfig) return null;

              // 如果是已保存的智能体，只有配置有变化时才显示"保存"按钮
              if (agentConfig?.agentId) {
                // 如果没有变化，不显示保存按钮
                if (!hasConfigChanges) return null;

                return (
                  <button
                    onClick={handleUpdateAgent}
                    disabled={isSavingAgent}
                    className={cn(
                      'w-full mt-4 py-2.5 px-4 rounded-xl',
                      'flex items-center justify-center gap-2',
                      'text-sm font-medium transition-all duration-200',
                      'border border-primary text-foreground',
                      'hover:bg-accent hover:text-accent-foreground',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                    )}
                  >
                    <Save size={14} />
                    <span>{isSavingAgent ? t('saving') : t('save')}</span>
                  </button>
                );
              }

              // 否则显示"保存为新智能体"
              return (
                <div className="mt-4 space-y-2">
                  <button
                    onClick={handleSaveAsNewAgent}
                    disabled={isSavingAgent}
                    className={cn(
                      'w-full py-2 px-4 rounded-lg',
                      'flex items-center justify-center gap-2',
                      'text-sm font-medium transition-all duration-200',
                      'border border-dashed border-border/60',
                      'text-muted-foreground hover:text-foreground',
                      'hover:border-primary/40 hover:bg-primary/5',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                    )}
                  >
                    <Save size={14} />
                    <span>{isSavingAgent ? t('savingAgent') : t('saveAsNewAgent')}</span>
                  </button>
                  <p className="text-xs text-center text-muted-foreground/70">{t('saveAsNewAgentTip')}</p>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* 智能体画廊（预置 + 自定义） - 懒加载 */}
      {!hideGallery && (
        <div className={cn(isConfigPanelExpanded && 'pt-2 border-t border-border/50')}>
          <Suspense fallback={<div className="h-32 animate-pulse bg-muted/50 rounded-lg" />}>
            <PresetAgentGallery
              onSelectPreset={handleSelectPreset}
              onSelectCustomAgent={(agent: { id: string }) => {
                clearPresetSelection(); // 清除预置智能体选中状态
                handleSelectAgent(agent);
              }}
              selectedPresetId={selectedPresetId}
              selectedAgentId={agentConfig?.agentId}
            />
          </Suspense>
        </div>
      )}

      {/* 编辑弹窗 - 懒加载 */}
      <Suspense fallback={null}>
        <AgentConfigEditDialog
          open={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          type={editDialogType}
          enabledSkills={enabledSkills}
          enabledMcps={enabledMcps}
          selectedSkillIds={agentConfig?.selectedSkillIds || []}
          skillConfigs={agentConfig?.skillConfigs || {}}
          selectedMcpNames={agentConfig?.selectedMcpNames || []}
          mcpToolSelections={agentConfig?.mcpToolSelections}
          systemPrompt={agentConfig?.systemPrompt || ''}
          useGlobalInstruction={agentConfig?.useGlobalInstruction ?? true}
          enabledBuiltinTools={currentBuiltinTools}
          browserEngine={agentConfig?.browserEngine}
          browserSource={agentConfig?.browserSource}
          dialogPolicy={agentConfig?.dialogPolicy}
          autoRestoreDomains={agentConfig?.autoRestoreDomains ?? EMPTY_AUTO_RESTORE_DOMAINS}
          ephemeralSubagents={agentConfig?.ephemeralSubagents || {}}
          onSave={handleSaveConfig}
          onRefreshSkills={refreshSkills}
        />
      </Suspense>
    </div>
  );
};

/**
 * 直连外部 Agent 选择器
 *
 * 从外部 agent 配置中读取已启用的 agent 列表，
 * 让用户选择后绕过主 LLM 直接路由到指定外部 agent。
 */
const DirectDelegateSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const [agents, setAgents] = useState<ExternalAgentConfig[]>([]);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  useEffect(() => {
    const syncManager = getConfigSyncManager();
    const val = syncManager.get('externalAgents');
    if (val?.agents) {
      setAgents(val.agents.filter((a) => a.enabled));
    }
  }, []);

  const selected = agentConfig?.forceDelegateAgent || '__off__';

  const handleChange = useCallback(
    (value: string) => {
      updateAgentConfig({ forceDelegateAgent: value === '__off__' ? undefined : value });
    },
    [updateAgentConfig],
  );

  if (agents.length === 0) return null;

  return (
    <div className="flex items-center gap-2 mt-3">
      <Zap size={14} className="text-amber-500 flex-shrink-0" />
      <span className="text-xs text-muted-foreground whitespace-nowrap">{t('directDelegate')}</span>
      <Select value={selected} onValueChange={handleChange}>
        <SelectTrigger
          className={cn(
            'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
            selected !== '__off__' && 'border-amber-400/50 bg-amber-50/30 dark:bg-amber-950/20',
          )}
        >
          <SelectValue placeholder={t('directDelegateOff')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__off__">{t('directDelegateOff')}</SelectItem>
          {agents.map((a) => (
            <SelectItem key={a.name} value={a.name}>
              {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
});
DirectDelegateSelector.displayName = 'DirectDelegateSelector';

/**
 * 场景化蓝图选择器 (JIT 一键编队)
 */
const BLUEPRINT_TEMPLATES = [
  {
    id: 'research_squad',
    subagents: {
      web_researcher: {
        display_name: 'Information Retrieval Specialist',
        system_prompt:
          'You are an information retrieval specialist responsible for using browsers and search engines to gather and summarize in-depth information from across the web.',
        tools: ['web_search', 'browser'],
        max_turns: 10,
        context_mode: 'fork',
      },
      data_analyst: {
        display_name: 'Data Synthesis Analyst',
        system_prompt:
          'You are a data analysis expert responsible for cross-validating, deduplicating, and deeply synthesizing retrieved information.',
        tools: [],
        max_turns: 5,
        context_mode: 'fork',
      },
    },
  },
  {
    id: 'code_audit_squad',
    subagents: {
      security_expert: {
        display_name: 'Security Defense Expert',
        system_prompt:
          'You are a top code security expert responsible for auditing code vulnerabilities (XSS, injection, privilege escalation, etc.).',
        tools: ['read_file', 'bash_run_command'],
        max_turns: 10,
        context_mode: 'fork',
      },
      perf_expert: {
        display_name: 'Performance Optimization Master',
        system_prompt:
          'You are a performance optimization master responsible for finding O(n^2) complexity, memory leaks, redundant rendering, and other performance defects.',
        tools: ['read_file', 'bash_run_command'],
        max_turns: 10,
        context_mode: 'fork',
      },
    },
  },
];

const ScenarioBlueprintSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  // 这里的 selected 用 ID 匹配 ephemeralSubagents
  const selected =
    agentConfig?.ephemeralSubagents && Object.keys(agentConfig.ephemeralSubagents).length > 0
      ? Object.keys(agentConfig.ephemeralSubagents).includes('web_researcher')
        ? 'research_squad'
        : Object.keys(agentConfig.ephemeralSubagents).includes('security_expert')
          ? 'code_audit_squad'
          : '__custom__'
      : '__off__';

  const [inheritMemory, setInheritMemory] = useState(true);

  const handleChange = useCallback(
    (value: string) => {
      if (value === '__off__') {
        updateAgentConfig({ ephemeralSubagents: {} });
        return;
      }
      const template = BLUEPRINT_TEMPLATES.find((t) => t.id === value);
      if (template) {
        // Apply current inheritMemory preference to the template
        const subagents = JSON.parse(JSON.stringify(template.subagents));
        Object.keys(subagents).forEach((key) => {
          subagents[key].context_mode = inheritMemory ? 'fork' : 'isolated';
        });
        updateAgentConfig({ ephemeralSubagents: subagents });
      }
    },
    [updateAgentConfig, inheritMemory],
  );

  const handleToggleInherit = useCallback(
    (checked: boolean) => {
      setInheritMemory(checked);
      if (selected !== '__off__' && agentConfig?.ephemeralSubagents) {
        const subagents = JSON.parse(JSON.stringify(agentConfig.ephemeralSubagents));
        Object.keys(subagents).forEach((key) => {
          subagents[key].context_mode = checked ? 'fork' : 'isolated';
        });
        updateAgentConfig({ ephemeralSubagents: subagents });
      }
    },
    [selected, agentConfig, updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-3">
      <div className="flex items-center gap-2">
        <AiNetworkIcon size={14} className="text-blue-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('jitTeam')}</span>
        <Select value={selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== '__off__' && 'border-blue-400/50 bg-blue-50/30 dark:bg-blue-950/20',
            )}
          >
            <SelectValue placeholder={t('jitTeamPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__off__">{t('jitTeamOff')}</SelectItem>
            {BLUEPRINT_TEMPLATES.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {t(`blueprints.${a.id}` as 'blueprints.research_squad' | 'blueprints.code_audit_squad')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selected !== '__off__' && (
        <div className="flex items-center gap-2 mt-1 ml-1 pl-5">
          <Switch checked={inheritMemory} onCheckedChange={handleToggleInherit} className="scale-75 origin-left" />
          <span className="text-xs text-muted-foreground">{t('jitInheritMemory')}</span>
        </div>
      )}
    </div>
  );
});
ScenarioBlueprintSelector.displayName = 'ScenarioBlueprintSelector';

/**
 * 记忆遗忘速度配置 (Memory Decay Selector)
 * 允许用户控制智能体长期记忆的衰减速度
 */
const MemoryDecaySelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  const selected = agentConfig?.memoryDecayProfile || 'normal';

  const handleChange = useCallback(
    (value: string) => {
      updateAgentConfig({ memoryDecayProfile: value as 'permanent' | 'normal' | 'fast' });
    },
    [updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-3">
      <div className="flex items-center gap-2">
        <IconBrain className="w-3.5 h-3.5 text-purple-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('memoryDecay')}</span>
        <Select value={selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== 'normal' && 'border-purple-400/50 bg-purple-50/30 dark:bg-purple-950/20',
            )}
          >
            <SelectValue placeholder={t('memoryDecayNormal')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="permanent">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayPermanent')}</span>
              </div>
            </SelectItem>
            <SelectItem value="normal">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayNormal')}</span>
              </div>
            </SelectItem>
            <SelectItem value="fast">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayFast')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
});
MemoryDecaySelector.displayName = 'MemoryDecaySelector';

export default memo(AgentConfigPanel);
