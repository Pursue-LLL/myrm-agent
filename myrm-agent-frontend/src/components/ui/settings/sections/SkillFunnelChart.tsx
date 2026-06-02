'use client';

import { useMemo } from 'react';

interface FunnelStage {
  label: string;
  count: number;
  rate: number; // 0-1
  color: string;
}

interface SkillFunnelChartProps {
  data: {
    total_selections: number;
    applied_count: number;
    completed_count: number;
    success_count: number;
  };
  width?: number;
  height?: number;
}

/**
 * Skill漏斗图（纯SVG实现）
 *
 * 展示Skill执行的4个阶段转化：
 * 1. Selected: 被选中次数（100%基准）
 * 2. Applied: 实际执行次数
 * 3. Completed: 完成次数（成功+失败）
 * 4. Success: 成功次数
 *
 * 用于诊断问题发生在哪个阶段：
 * - 高fallback率：Selected多但Applied少
 * - 高中断率：Applied多但Completed少
 * - 高失败率：Completed多但Success少
 */
export function SkillFunnelChart({ data, width = 300, height = 240 }: SkillFunnelChartProps) {
  const stages: FunnelStage[] = useMemo(() => {
    const { total_selections, applied_count, completed_count, success_count } = data;

    if (total_selections === 0) {
      return [];
    }

    return [
      {
        label: 'Selected',
        count: total_selections,
        rate: 1.0,
        color: 'rgb(59, 130, 246)', // blue-500
      },
      {
        label: 'Applied',
        count: applied_count,
        rate: applied_count / total_selections,
        color: 'rgb(99, 102, 241)', // indigo-500
      },
      {
        label: 'Completed',
        count: completed_count,
        rate: completed_count / total_selections,
        color: 'rgb(139, 92, 246)', // violet-500
      },
      {
        label: 'Success',
        count: success_count,
        rate: success_count / total_selections,
        color: 'rgb(34, 197, 94)', // green-500
      },
    ];
  }, [data]);

  if (stages.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground" style={{ width, height }}>
        No data available
      </div>
    );
  }

  const padding = 20;
  const stageHeight = (height - padding * 2) / stages.length;
  const maxWidth = width - padding * 2;

  return (
    <div className="relative" style={{ width, height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {stages.map((stage, index) => {
          const stageWidth = maxWidth * stage.rate;
          const x = padding + (maxWidth - stageWidth) / 2;
          const y = padding + index * stageHeight;

          return (
            <g key={index}>
              {/* 漏斗阶段矩形 */}
              <rect x={x} y={y} width={stageWidth} height={stageHeight * 0.8} fill={stage.color} opacity={0.8} rx={4} />

              {/* 文本标签 */}
              <text
                x={width / 2}
                y={y + stageHeight * 0.25}
                textAnchor="middle"
                fill="white"
                fontSize="12"
                fontWeight="600"
              >
                {stage.label}
              </text>

              {/* 数量和百分比 */}
              <text
                x={width / 2}
                y={y + stageHeight * 0.5}
                textAnchor="middle"
                fill="white"
                fontSize="14"
                fontWeight="bold"
              >
                {stage.count}
              </text>

              <text
                x={width / 2}
                y={y + stageHeight * 0.65}
                textAnchor="middle"
                fill="white"
                fontSize="11"
                opacity={0.9}
              >
                ({(stage.rate * 100).toFixed(1)}%)
              </text>
            </g>
          );
        })}

        {/* 连接线（显示流失） */}
        {stages.slice(0, -1).map((stage, index) => {
          const nextStage = stages[index + 1];
          const currentWidth = maxWidth * stage.rate;
          const nextWidth = maxWidth * nextStage.rate;
          const currentX = padding + (maxWidth - currentWidth) / 2;
          const nextX = padding + (maxWidth - nextWidth) / 2;
          const currentY = padding + index * stageHeight + stageHeight * 0.8;
          const nextY = padding + (index + 1) * stageHeight;

          return (
            <g key={`connector-${index}`}>
              <line
                x1={currentX}
                y1={currentY}
                x2={nextX}
                y2={nextY}
                stroke="currentColor"
                strokeWidth="1"
                className="text-muted-foreground/30"
                strokeDasharray="2,2"
              />
              <line
                x1={currentX + currentWidth}
                y1={currentY}
                x2={nextX + nextWidth}
                y2={nextY}
                stroke="currentColor"
                strokeWidth="1"
                className="text-muted-foreground/30"
                strokeDasharray="2,2"
              />
            </g>
          );
        })}
      </svg>

      {/* 图例 */}
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        <div>Fallback Rate: {((1 - stages[1].rate) * 100).toFixed(1)}%</div>
        <div>
          Interruption Rate: {stages[1].rate > 0 ? ((1 - stages[2].rate / stages[1].rate) * 100).toFixed(1) : 0}%
        </div>
        <div>Failure Rate: {stages[2].rate > 0 ? ((1 - stages[3].rate / stages[2].rate) * 100).toFixed(1) : 0}%</div>
      </div>
    </div>
  );
}
