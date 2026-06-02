'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { Settings, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { PresetAgent } from '@/types/presetAgent';
import type { AgentListItem } from '@/services/agent';
import { useAgentGallery } from '@/hooks/useAgentGallery';
import { GalleryBackground } from './GalleryBackground';
import PresetAgentCard from './PresetAgentCard';
import CustomAgentCard from './CustomAgentCard';
import TemplateMarket from './TemplateMarket';

interface PresetAgentGalleryProps {
  onSelectPreset: (agent: PresetAgent, workingDirectory?: string) => void;
  onSelectCustomAgent?: (agent: AgentListItem) => void;
  selectedPresetId?: string;
  selectedAgentId?: string;
  /** CLI 智能体的工作目录 */
  workingDirectory?: string;
  className?: string;
}

const isCLIVisualAgent = (agent: PresetAgent) => {
  return agent.category === 'cli_visual' && agent.requiresWorkingDirectory === true;
};

/**
 * 预置智能体画廊组件
 * 展示预置智能体和用户自定义智能体
 */
const PresetAgentGallery = ({
  onSelectPreset,
  onSelectCustomAgent,
  selectedPresetId,
  selectedAgentId,
  workingDirectory: externalWorkingDirectory,
  className,
}: PresetAgentGalleryProps) => {
  const t = useTranslations('presetAgent');
  const tAgent = useTranslations('agent');
  const router = useRouter();

  // 使用自定义Hook管理状态和逻辑
  const {
    presetAgents,
    customAgents,
    handlePresetClick,
    handleCustomAgentClick,
    workingDirectory: effectiveWorkingDirectory,
    handleWorkingDirectoryChange,
    cliCardRef,
  } = useAgentGallery({
    onSelectPreset,
    onSelectCustomAgent,
    externalWorkingDirectory,
  });

  return (
    <div className={cn('relative overflow-hidden', className)}>
      {/* 泼墨背景效果 - 紫色系 */}
      <GalleryBackground />

      <div className="relative z-10 space-y-4 py-4 px-2">
        {/* 标题行 */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground/80">{t('title')}</span>
          </div>
          {/* 管理入口 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push('/settings/agents')}
            className="text-xs text-muted-foreground hover:text-foreground h-auto py-1 px-2 gap-1"
          >
            <Settings size={12} />
            {tAgent('configPanel.manage')}
            <ChevronRight size={12} />
          </Button>
        </div>

        {/* 预置智能体卡片 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {presetAgents.map((agent) => (
            <PresetAgentCard
              key={agent.id}
              agent={agent}
              isSelected={selectedPresetId === agent.id}
              onSelect={handlePresetClick}
              workingDirectory={isCLIVisualAgent(agent) ? effectiveWorkingDirectory : undefined}
              onWorkingDirectoryChange={isCLIVisualAgent(agent) ? handleWorkingDirectoryChange : undefined}
              cardRef={isCLIVisualAgent(agent) ? cliCardRef : undefined}
            />
          ))}
        </div>

        {/* 模板市场 */}
        <TemplateMarket />

        {/* 用户自定义智能体区块 */}
        {customAgents.length > 0 && (
          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-2 px-1">
              <div className="flex-1 h-px bg-border/50" />
              <span className="text-xs text-muted-foreground">{tAgent('configPanel.savedAgents')}</span>
              <div className="flex-1 h-px bg-border/50" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {customAgents.map((agent) => (
                <CustomAgentCard
                  key={agent.id}
                  agent={agent}
                  isSelected={selectedAgentId === agent.id}
                  onClick={() => handleCustomAgentClick(agent)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * 性能优化：使用 React.memo 避免不必要的重渲染
 *
 * 仅在以下情况重新渲染：
 * - onSelectPreset 函数引用变化
 * - onSelectCustomAgent 函数引用变化
 * - selectedPresetId 变化
 * - selectedAgentId 变化
 */
export default memo(PresetAgentGallery);
