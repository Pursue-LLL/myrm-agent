/**
 * Interactive Callout Chip Component
 * 对话气泡与长文报告内嵌的交互式空间引文芯片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 语义标准与键盘可访问性；
 * 5. 行数严格受控在 200 行以内。
 */

import React from 'react';
import {
  AlertTriangle,
  Box,
  Code2,
  Crosshair,
  Info,
  Layout,
  Palette,
} from 'lucide-react';
import {
  CalloutAnchor,
  CalloutEvidenceType,
  CalloutSeverity,
} from './calloutAnchorTypes';
import { useCalloutAnchorStore } from './useCalloutAnchorStore';

export interface InteractiveCalloutChipProps {
  anchor: CalloutAnchor;
  className?: string;
}

export const InteractiveCalloutChip: React.FC<InteractiveCalloutChipProps> = ({
  anchor,
  className = '',
}) => {
  const { activeAnchorId, focusAnchor, setHoveredAnchorId } =
    useCalloutAnchorStore();

  const isActive = activeAnchorId === anchor.id;

  const renderEvidenceIcon = (type: CalloutEvidenceType): React.ReactElement => {
    if (type === '3d') {
      return <Box className="h-3 w-3 text-indigo-400" />;
    }
    if (type === 'code') {
      return <Code2 className="h-3 w-3 text-emerald-400" />;
    }
    if (type === 'dom') {
      return <Layout className="h-3 w-3 text-amber-400" />;
    }
    return <Palette className="h-3 w-3 text-cyan-400" />;
  };

  const getSeverityBadgeClass = (severity: CalloutSeverity): string => {
    if (severity === 'critical') {
      return 'border-rose-500/50 bg-rose-950/30 text-rose-300';
    }
    if (severity === 'warning') {
      return 'border-amber-500/50 bg-amber-950/30 text-amber-300';
    }
    return 'border-indigo-500/50 bg-indigo-950/30 text-indigo-300';
  };

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    focusAnchor(anchor.id, 'chip');
  };

  return (
    <button
      type="button"
      data-testid={`callout-chip-${anchor.id}`}
      aria-pressed={isActive}
      onClick={handleClick}
      onMouseEnter={() => {
        setHoveredAnchorId(anchor.id);
      }}
      onMouseLeave={() => {
        setHoveredAnchorId(null);
      }}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all duration-150 select-none cursor-pointer ${getSeverityBadgeClass(
        anchor.severity
      )} ${
        isActive
          ? 'ring-2 ring-indigo-500 ring-offset-1 ring-offset-neutral-950 shadow-md shadow-indigo-500/20 scale-[1.02]'
          : 'hover:scale-[1.01] hover:brightness-110 opacity-90'
      } ${className}`}
      title={`点击聚焦右侧工件视口中的构件 [${anchor.targetSelector}]`}
    >
      <span className="flex items-center">{renderEvidenceIcon(anchor.evidenceType)}</span>
      <span className="font-sans text-[11px] font-semibold">{anchor.label}</span>

      {isActive ? (
        <span
          data-testid="chip-focused-badge"
          className="flex items-center gap-0.5 rounded-full bg-indigo-500/30 px-1 text-[9px] text-indigo-200 animate-pulse font-mono"
        >
          <Crosshair className="h-2.5 w-2.5" />
          <span>聚焦中</span>
        </span>
      ) : (
        <span className="text-[10px] text-neutral-400 font-mono">
          {anchor.severity === 'critical' ? (
            <AlertTriangle className="h-2.5 w-2.5 text-rose-400" />
          ) : (
            <Info className="h-2.5 w-2.5 text-neutral-400" />
          )}
        </span>
      )}
    </button>
  );
};
