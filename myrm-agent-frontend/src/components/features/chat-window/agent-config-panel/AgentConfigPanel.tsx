'use client';

import { memo, lazy, Suspense, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Save } from 'lucide-react';
import AgentConfigCards from './AgentConfigCards';
import TypewriterWelcome from './TypewriterWelcome';
import DirectDelegateSelector from './DirectDelegateSelector';
import ScenarioBlueprintSelector from './ScenarioBlueprintSelector';
import { MemoryDecaySelector, MemoryExtractionPresetSelector } from './MemorySelectors';
import { useAgentConfigPanel } from '@/hooks/agent/useAgentConfigPanel';
import { useChatTurnPrewarm } from '@/hooks/chat/useChatTurnPrewarm';

// 懒加载大型组件，减少初始加载时间
const AgentConfigEditDialog = lazy(() => import('./AgentConfigEditDialog'));
const EMPTY_AUTO_RESTORE_DOMAINS: string[] = [];

interface AgentConfigPanelProps {
  /** 作用于展开后的编辑面板；折叠时面板不占任何高度 */
  className?: string;
}

/**
 * 智能体配置面板主容器
 * 仅在智能代理模式下显示
 * 包含：编辑面板（四个配置卡片）
 */
const AgentConfigPanel = ({ className }: AgentConfigPanelProps) => {
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

    // Handlers
    setEditDialogOpen,
    handleCardClick,
    handleSaveConfig,
    handleSaveAsNewAgent,
    handleUpdateAgent,
    handleTypewriterComplete,

    refreshSkills,

    // Translations
    t,
    tIndicator,
  } = useAgentConfigPanel();

  const { triggerPrewarm } = useChatTurnPrewarm();

  useEffect(() => {
    if (actionMode === 'agent' && agentConfig?.agentId) {
      void triggerPrewarm();
    }
  }, [actionMode, agentConfig?.agentId, triggerPrewarm]);

  // 仅在智能代理模式下显示
  if (actionMode !== 'agent') {
    return null;
  }

  return (
    <div className="relative w-full overflow-visible">
      <div className="relative z-10 space-y-6">
        {/* 编辑面板区域 - 根据展开状态显示/隐藏 */}
        {isConfigPanelExpanded && (
          <div
            className={cn('relative py-4 px-2', 'animate-in fade-in-50 slide-in-from-top-2 duration-300', className)}
          >
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
              <MemoryExtractionPresetSelector />

              {/* 保存按钮逻辑 */}
              {(() => {
                const hasConfig =
                  (agentConfig?.selectedSkillIds?.length || 0) > 0 ||
                  (agentConfig?.selectedMcpNames?.length || 0) > 0 ||
                  (agentConfig?.systemPrompt?.trim().length || 0) > 0;

                // 如果没有任何配置，不显示按钮
                if (!hasConfig) {
                  return null;
                }

                // 如果是已保存的智能体，只有配置有变化时才显示"保存"按钮
                if (agentConfig?.agentId) {
                  // 如果没有变化，不显示保存按钮
                  if (!hasConfigChanges) {
                    return null;
                  }

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
      </div>

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

export default memo(AgentConfigPanel);
