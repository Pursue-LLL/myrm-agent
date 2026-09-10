'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (POS: 活跃技能与单轮覆盖状态)
 * - @/store/skill::useSkillStore (POS: 技能元数据字典，包含 required_oauth_issuers / required_mcp_server_ids)
 * - @/store/useConfigStore (POS: MCP 服务配置状态)
 * - @/lib/skills/integrationOAuthDisplay (POS: OAuth 设置路径与映射)
 *
 * [OUTPUT]
 * - SkillRequiredConnectorsPreflightBanner: 技能依赖连接器前置主动预检与轻量挂载建议条
 *
 * [POS]
 * 在输入区上方呈现。当用户启用的 Skill 声明了前置 OAuth / MCP 依赖且尚未满足时，
 * 主动提示缺少连接器并提供「前往授权」和「单轮收窄工具」快捷入口，杜绝盲目挂载导致的调用幻觉。
 */

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Link2, SlidersHorizontal, CheckCircle2, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { useSkillStore } from '@/store/skill';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import {
  SETTINGS_GOOGLE_OAUTH_PATH,
  SETTINGS_SKILLS_PATH,
} from '@/lib/skills/integrationOAuthDisplay';

export interface SkillRequiredConnectorsPreflightBannerProps {
  className?: string;
  onOpenCapabilityEditor?: () => void;
}

export function SkillRequiredConnectorsPreflightBanner({
  className,
  onOpenCapabilityEditor,
}: SkillRequiredConnectorsPreflightBannerProps) {
  const t = useTranslations('chat.skillConnectorsPreflight');
  const router = useRouter();

  const { agentConfig, turnCapabilitySelection } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      turnCapabilitySelection: state.turnCapabilitySelection,
    })),
  );

  const { marketSkills, localSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
    })),
  );

  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);

  // 1. 解析当前生效的技能集合 (优先使用单轮收窄 selection，其次为 AgentConfig)
  const activeSkillIds = useMemo(() => {
    if (turnCapabilitySelection?.skillIds !== null && turnCapabilitySelection?.skillIds !== undefined) {
      return turnCapabilitySelection.skillIds;
    }
    return agentConfig?.selectedSkillIds ?? [];
  }, [agentConfig?.selectedSkillIds, turnCapabilitySelection?.skillIds]);

  // 2. 预检依赖缺失情况
  const preflightResult = useMemo(() => {
    if (activeSkillIds.length === 0) {
      return null;
    }

    const allSkills = [...marketSkills, ...localSkills];
    const skillMap = new Map(allSkills.map((s) => [s.id, s]));

    const missingIssuers: Array<{ skillName: string; issuer: string }> = [];
    const missingMcp: Array<{ skillName: string; serverId: string }> = [];

    const activeMcpIds = new Set(
      mcpConfigs.filter((cfg) => cfg.enabled !== false).map((cfg) => cfg.id || cfg.name),
    );

    for (const skillId of activeSkillIds) {
      const skill = skillMap.get(skillId);
      if (!skill) continue;

      // 检查 OAuth issuers
      const requiredIssuers = skill.required_oauth_issuers ?? (skill.oauth_issuer ? [skill.oauth_issuer] : []);
      if (!skill.available && requiredIssuers.length > 0) {
        for (const issuer of requiredIssuers) {
          missingIssuers.push({ skillName: skill.name, issuer });
        }
      }

      // 检查 MCP Server 依赖
      const requiredMcpServers = skill.required_mcp_server_ids ?? [];
      for (const srvId of requiredMcpServers) {
        if (!activeMcpIds.has(srvId)) {
          missingMcp.push({ skillName: skill.name, serverId: srvId });
        }
      }
    }

    if (missingIssuers.length === 0 && missingMcp.length === 0) {
      return null;
    }

    return {
      missingIssuers,
      missingMcp,
      totalMissing: missingIssuers.length + missingMcp.length,
    };
  }, [activeSkillIds, marketSkills, localSkills, mcpConfigs]);

  if (!preflightResult) {
    return null;
  }

  const handleGoToSettings = () => {
    if (preflightResult.missingIssuers.some((i) => i.issuer.toLowerCase().includes('google'))) {
      router.push(SETTINGS_GOOGLE_OAUTH_PATH);
    } else {
      router.push(SETTINGS_SKILLS_PATH);
    }
  };

  return (
    <div
      data-testid="skill-connectors-preflight-banner"
      className={cn(
        'flex items-center justify-between gap-3 px-3.5 py-2 mb-2 rounded-lg border text-xs transition-all',
        'border-amber-500/30 bg-amber-500/[0.08] text-amber-900 dark:text-amber-200',
        className,
      )}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <AlertCircle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="flex items-center gap-1.5 truncate">
          <span className="font-medium shrink-0">{t('missingNotice')}:</span>
          <span className="truncate text-muted-foreground/90">
            {preflightResult.missingIssuers.map((i) => `${i.skillName} (${i.issuer})`).join(', ')}
            {preflightResult.missingMcp.map((m) => `${m.skillName} [MCP: ${m.serverId}]`).join(', ')}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {onOpenCapabilityEditor && (
          <button
            type="button"
            onClick={onOpenCapabilityEditor}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-background/80 hover:bg-background text-foreground border border-border/80 shadow-2xs font-medium cursor-pointer transition-colors"
          >
            <SlidersHorizontal className="size-3" />
            <span>{t('narrowScopeAction')}</span>
          </button>
        )}
        <button
          type="button"
          onClick={handleGoToSettings}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-primary text-primary-foreground font-medium shadow-2xs hover:bg-primary/90 cursor-pointer transition-colors"
        >
          <Link2 className="size-3" />
          <span>{t('connectAction')}</span>
        </button>
      </div>
    </div>
  );
}

export default SkillRequiredConnectorsPreflightBanner;
