import React, { useState } from 'react';
import {
  Clock,
  Zap,
  ArrowRightLeft,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { TurnOriginType, TurnProvenanceMeta } from './turnLineageTypes';
import { getOriginVisualTheme } from './turnLineageEngine';
import { TurnProvenanceHoverCard } from './TurnProvenanceHoverCard';
import { useTurnLineageStore } from './useTurnLineageStore';

interface TurnOriginBadgeProps {
  turnId: string;
  provenance: TurnProvenanceMeta;
  tokensUsed?: number;
  durationMs?: number;
  isCompact?: boolean;
}

export const TurnOriginBadge: React.FC<TurnOriginBadgeProps> = ({
  turnId,
  provenance,
  tokensUsed,
  durationMs,
  isCompact = false,
}) => {
  const { selectTurn, highlightedLineageChain } = useTurnLineageStore();
  const [isHovered, setIsHovered] = useState(false);

  const theme = getOriginVisualTheme(provenance.originType);
  const isInHighlightedChain = highlightedLineageChain.includes(turnId);

  const getIcon = (type: TurnOriginType) => {
    switch (type) {
      case 'cron_job':
        return <Clock className="w-3 h-3 text-purple-400" />;
      case 'webhook_trigger':
        return <Zap className="w-3 h-3 text-amber-400" />;
      case 'subagent_delegation':
        return <ArrowRightLeft className="w-3 h-3 text-indigo-400" />;
      case 'approval_resume':
        return <ShieldCheck className="w-3 h-3 text-emerald-400" />;
      default:
        return <Terminal className="w-3 h-3 text-slate-400" />;
    }
  };

  const getDisplayLabel = () => {
    if (isCompact) {
      return theme.label;
    }
    switch (provenance.originType) {
      case 'cron_job':
        return `Cron: ${provenance.originRefId.replace('cron:', '')}`;
      case 'webhook_trigger':
        return 'Webhook 触发';
      case 'subagent_delegation':
        return `移交: ${provenance.executedByAgent}`;
      case 'approval_resume':
        return '审批通过放行';
      default:
        return '人工直接指令';
    }
  };

  return (
    <div
      className="relative inline-block select-none"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <button
        type="button"
        onClick={() => selectTurn(turnId)}
        data-testid="turn-origin-badge"
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-medium transition-all cursor-pointer ${
          theme.badgeBg
        } ${theme.badgeBorder} ${theme.badgeText} ${
          isInHighlightedChain
            ? 'ring-2 ring-indigo-500 shadow-md scale-105'
            : 'hover:border-slate-500'
        }`}
        title="点击追溯全链路因果链"
        aria-label={`轮次触发源: ${theme.label}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${theme.dotColor}`} />
        {getIcon(provenance.originType)}
        <span>{getDisplayLabel()}</span>
      </button>

      {/* 悬停详述卡片 */}
      {isHovered && (
        <div className="absolute left-0 top-6 z-40">
          <TurnProvenanceHoverCard
            provenance={provenance}
            tokensUsed={tokensUsed}
            durationMs={durationMs}
          />
        </div>
      )}
    </div>
  );
};
