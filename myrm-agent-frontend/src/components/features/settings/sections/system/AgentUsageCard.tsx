'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Layers, Globe, Bot, Clock, MessageSquare } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { getAgentUsage, type AgentUsageItem } from '@/services/statistics';
import { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import { cn } from '@/lib/utils/classnameUtils';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

const SPARKLINE_WIDTH = 80;
const SPARKLINE_HEIGHT = 24;

const MiniSparkline = memo<{ data: number[]; className?: string }>(({ data, className }) => {
  if (data.length < 2 || data.every((v) => v === 0)) {
    return null;
  }
  const max = Math.max(...data, 1);
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * SPARKLINE_WIDTH;
    const y = SPARKLINE_HEIGHT - (v / max) * SPARKLINE_HEIGHT;
    return `${x},${y}`;
  });
  const pathD = `M${points.join(' L')}`;
  return (
    <svg
      width={SPARKLINE_WIDTH}
      height={SPARKLINE_HEIGHT}
      viewBox={`0 0 ${SPARKLINE_WIDTH} ${SPARKLINE_HEIGHT}`}
      className={cn('shrink-0', className)}
    >
      <path
        d={pathD}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
});
MiniSparkline.displayName = 'MiniSparkline';

const AgentUsageCard = memo(() => {
  const t = useTranslations('settings.usageStatistics');
  const locale = useLocale();
  const [agents, setAgents] = useState<AgentUsageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getAgentUsage(7);
      setAgents(res.agents);
    } catch {
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  if (loading) {
    return null;
  }
  if (agents.length === 0) {
    return null;
  }

  const maxUsd = Math.max(...agents.map((a) => a.totalUsd), 0.001);

  return (
    <SettingsSection title={t('agentUsageTitle') || 'Agent Usage Breakdown'}>
      <div className="space-y-3">
        {agents.map((agent, idx) => {
          const barWidth = (agent.totalUsd / maxUsd) * 100;
          const sparklineData = agent.sparkline.map((s) => s.tokens);
          const isExpanded = expandedAgentId === agent.agentId;
          const attr = agent.attribution;

          return (
            <motion.div
              key={agent.agentId}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05 }}
              className={cn(
                'group flex flex-col p-2.5 sm:p-3 rounded-xl border border-border/40 bg-background/60',
                'hover:border-primary/20 hover:bg-background/80 transition-all',
              )}
            >
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 overflow-hidden">
                  {agent.avatar ? (
                    <img
                      src={agent.avatar}
                      alt={getBuiltinAgentName(agent.agentId, agent.name || agent.agentId, locale)}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-xs font-bold text-primary">
                      {getBuiltinAgentName(agent.agentId, agent.name || agent.agentId, locale)
                        .charAt(0)
                        .toUpperCase()}
                    </span>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-foreground truncate">
                      {getBuiltinAgentName(agent.agentId, agent.name || agent.agentId, locale)}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                      {agent.percentUsd.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted/50 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary/70 to-primary transition-all duration-500"
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
                    <span>{formatCost(agent.totalUsd)}</span>
                    <span>{formatTokenCount(agent.totalTokens)} tokens</span>
                    <span>
                      {agent.totalCalls} {t('calls') || 'calls'}
                    </span>
                  </div>
                </div>

                <MiniSparkline data={sparklineData} className="text-primary/60 hidden sm:block" />

                <button
                  type="button"
                  data-testid={`toggle-why-spent-${agent.agentId}`}
                  onClick={() => setExpandedAgentId(isExpanded ? null : agent.agentId)}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors ml-1"
                  title={t('whySpent')}
                >
                  {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden pt-2.5 mt-2.5 border-t border-border/40"
                  >
                    <div className="flex items-center gap-1.5 text-xs font-medium text-foreground mb-2">
                      <Layers className="w-3.5 h-3.5 text-primary" />
                      <span>{t('whySpent')}</span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <div className="p-2 rounded-lg bg-background/80 border border-border/40 flex flex-col gap-0.5">
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Globe className="w-3 h-3 text-sky-500" />
                          <span>{t('sourceWeb')}</span>
                        </div>
                        <span className="text-xs font-semibold text-foreground">{formatCost(attr?.webUsd ?? 0)}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {formatTokenCount(attr?.webTokens ?? 0)} tokens
                        </span>
                      </div>

                      <div className="p-2 rounded-lg bg-background/80 border border-border/40 flex flex-col gap-0.5">
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Bot className="w-3 h-3 text-purple-500" />
                          <span>{t('sourceSubagents')}</span>
                        </div>
                        <span className="text-xs font-semibold text-foreground">
                          {formatCost(attr?.subagentsUsd ?? 0)}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {formatTokenCount(attr?.subagentsTokens ?? 0)} tokens
                        </span>
                      </div>

                      <div className="p-2 rounded-lg bg-background/80 border border-border/40 flex flex-col gap-0.5">
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Clock className="w-3 h-3 text-amber-500" />
                          <span>{t('sourceCron')}</span>
                        </div>
                        <span className="text-xs font-semibold text-foreground">{formatCost(attr?.cronUsd ?? 0)}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {formatTokenCount(attr?.cronTokens ?? 0)} tokens
                        </span>
                      </div>

                      <div className="p-2 rounded-lg bg-background/80 border border-border/40 flex flex-col gap-0.5">
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <MessageSquare className="w-3 h-3 text-emerald-500" />
                          <span>{t('sourceChannel')}</span>
                        </div>
                        <span className="text-xs font-semibold text-foreground">
                          {formatCost(attr?.channelUsd ?? 0)}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {formatTokenCount(attr?.channelTokens ?? 0)} tokens
                        </span>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
    </SettingsSection>
  );
});
AgentUsageCard.displayName = 'AgentUsageCard';

export default AgentUsageCard;
