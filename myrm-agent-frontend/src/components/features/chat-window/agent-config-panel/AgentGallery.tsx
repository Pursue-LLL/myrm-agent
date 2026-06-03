'use client';

import { useTranslations } from 'next-intl';
import { AgentListItem, Agent, getAgent } from '@/services/agent';
import { cn } from '@/lib/utils/classnameUtils';
import { ChevronRight } from 'lucide-react';
import { AiNetworkIcon } from 'hugeicons-react';
import { Button } from '@/components/primitives/button';
import { useMemo, useState, useCallback } from 'react';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import AgentBrickCard, { type ConfigNameMaps } from './AgentBrickCard';

interface AgentGalleryProps {
  agents: AgentListItem[];
  onSelectAgent: (agent: AgentListItem) => void;
  onViewAll?: () => void;
  className?: string;
  maxVisible?: number;
  selectedAgentId?: string;
}

/**
 * 已保存智能体画廊组件
 * 采用砖墙式错落布局 + 泼墨背景 + 毛玻璃卡片
 */
const AgentGallery = ({
  agents,
  onSelectAgent,
  onViewAll,
  className,
  maxVisible = 12,
  selectedAgentId,
}: AgentGalleryProps) => {
  const t = useTranslations('agent.configPanel');

  // 缓存已加载的智能体详情
  const [agentDetailsCache, setAgentDetailsCache] = useState<Map<string, Agent>>(new Map());

  // 从 store 获取技能和 MCP 信息（包括本地技能）
  const { marketSkills, localSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
    })),
  );

  const { mcpConfigs } = useConfigStore(
    useShallow((state) => ({
      mcpConfigs: state.mcpConfigs,
    })),
  );

  // 构建名称映射
  const configNameMaps = useMemo<ConfigNameMaps>(() => {
    const skillMap = new Map<string, string>();
    const mcpMap = new Map<string, string>();

    [...marketSkills, ...localSkills].forEach((skill) => {
      skillMap.set(skill.id, skill.name);
    });

    mcpConfigs.forEach((mcp) => {
      mcpMap.set(mcp.name, mcp.name);
    });

    return { skills: skillMap, mcps: mcpMap };
  }, [marketSkills, localSkills, mcpConfigs]);

  const visibleAgents = agents.slice(0, maxVisible);

  // 加载智能体详情
  const loadAgentDetails = useCallback(
    async (agentId: string): Promise<Agent | null> => {
      // 先检查缓存
      if (agentDetailsCache.has(agentId)) {
        return agentDetailsCache.get(agentId) || null;
      }

      try {
        const details = await getAgent(agentId);
        setAgentDetailsCache((prev) => {
          const newCache = new Map(prev);
          newCache.set(agentId, details);
          return newCache;
        });
        return details;
      } catch {
        return null;
      }
    },
    [agentDetailsCache],
  );

  if (agents.length === 0) {
    return (
      <div
        className={cn(
          'relative py-8 px-6 rounded-2xl text-center',
          'bg-gradient-to-br from-muted/20 via-transparent to-muted/20',
          'border border-border/20',
        )}
      >
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-muted/30 mb-3">
          <AiNetworkIcon size={20} className="text-muted-foreground/50" />
        </div>
        <p className="text-sm text-muted-foreground">{t('noSavedAgents')}</p>
        <p className="text-xs text-muted-foreground/60 mt-1">{t('noSavedAgentsDesc')}</p>
      </div>
    );
  }

  return (
    <div className={cn('relative overflow-hidden', className)}>
      {/* 泼墨背景效果 - 与能力配置区保持一致的暖色系 */}
      <div
        className="absolute pointer-events-none"
        style={{
          inset: '-20px -30px -15px -30px',
          zIndex: 0,
        }}
      >
        <svg
          className="w-full h-full"
          viewBox="0 0 500 200"
          preserveAspectRatio="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* #fefef8 暖色系渐变 - 米黄/奶油色调（与能力配置区一致） */}
            <linearGradient id="agentInkGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#fefef8" stopOpacity="0.5" />
              <stop offset="30%" stopColor="#fdf9e6" stopOpacity="0.6" />
              <stop offset="60%" stopColor="#fefcf3" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#fefef8" stopOpacity="0.4" />
            </linearGradient>
            {/* 柔和的模糊效果 */}
            <filter id="agentInkBlur" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* 主泼墨形状 - 不规则曲线 */}
          <path
            d="M35,40
               C80,15 140,25 200,20
               C280,14 350,28 420,24
               C465,21 490,50 480,90
               C485,130 475,165 445,185
               C390,200 300,195 200,190
               C110,188 45,180 20,155
               C5,130 10,85 35,40 Z"
            fill="url(#agentInkGradient)"
            filter="url(#agentInkBlur)"
          />

          {/* 溢出的小墨滴 - 暖色系 */}
          <ellipse cx="470" cy="50" rx="18" ry="12" fill="#fdf9e6" fillOpacity="0.4" />
          <ellipse cx="25" cy="160" rx="15" ry="10" fill="#fefcf3" fillOpacity="0.4" />
          <circle cx="480" cy="130" r="12" fill="#fefef8" fillOpacity="0.35" />
        </svg>
      </div>

      <div className="relative z-10 space-y-4 py-4 px-2">
        {/* 标题行 */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground/80">{t('savedAgents')}</span>
            <span className="text-xs text-muted-foreground bg-muted/40 px-2 py-0.5 rounded-full">{agents.length}</span>
          </div>
          {onViewAll && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onViewAll}
              className="text-xs text-muted-foreground/60 hover:text-primary h-auto py-1 px-2 gap-0.5"
            >
              {t('manage')}
              <ChevronRight size={12} />
            </Button>
          )}
        </div>

        {/* 智能体卡片 - 响应式网格布局：移动端1列，平板2列，PC端使用flex流式 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:flex lg:flex-wrap gap-3 items-start">
          {visibleAgents.map((agent, index) => (
            <AgentBrickCard
              key={agent.id}
              agent={agent}
              index={index}
              onClick={() => onSelectAgent(agent)}
              onLoadDetails={loadAgentDetails}
              cachedDetails={agentDetailsCache.get(agent.id)}
              configNameMaps={configNameMaps}
              isSelected={selectedAgentId === agent.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default AgentGallery;
