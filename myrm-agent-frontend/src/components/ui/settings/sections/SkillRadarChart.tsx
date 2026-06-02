'use client';

import { useMemo } from 'react';

interface RadarChartProps {
  data: {
    label: string;
    value: number; // 0-1
  }[];
  size?: number;
}

/**
 * Skill质量雷达图（纯SVG实现）
 *
 * 5维质量评分可视化：
 * - success_rate: 成功率
 * - token_efficiency: Token效率
 * - response_time: 响应时间
 * - complexity_score: 复杂度评分
 * - user_satisfaction: 用户满意度
 */
export function SkillRadarChart({ data, size = 200 }: RadarChartProps) {
  const center = size / 2;
  const maxRadius = size * 0.4;
  const levels = 5;

  const points = useMemo(() => {
    const angleStep = (2 * Math.PI) / data.length;
    return data.map((item, index) => {
      const angle = angleStep * index - Math.PI / 2;
      const radius = maxRadius * item.value;
      return {
        x: center + radius * Math.cos(angle),
        y: center + radius * Math.sin(angle),
        label: item.label,
        value: item.value,
        angle,
      };
    });
  }, [data, center, maxRadius]);

  const gridLevels = useMemo(() => {
    return Array.from({ length: levels }, (_, i) => {
      const radius = maxRadius * ((i + 1) / levels);
      const angleStep = (2 * Math.PI) / data.length;
      return data.map((_, index) => {
        const angle = angleStep * index - Math.PI / 2;
        return {
          x: center + radius * Math.cos(angle),
          y: center + radius * Math.sin(angle),
        };
      });
    });
  }, [data.length, center, maxRadius, levels]);

  const pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ') + ' Z';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 背景网格 */}
        {gridLevels.map((level, levelIndex) => (
          <polygon
            key={levelIndex}
            points={level.map((p) => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            className="text-muted-foreground/20"
          />
        ))}

        {/* 轴线 */}
        {points.map((p, index) => (
          <line
            key={index}
            x1={center}
            y1={center}
            x2={center + maxRadius * Math.cos(p.angle)}
            y2={center + maxRadius * Math.sin(p.angle)}
            stroke="currentColor"
            strokeWidth="0.5"
            className="text-muted-foreground/30"
          />
        ))}

        {/* 数据区域 */}
        <path d={pathData} className="fill-primary/30 stroke-primary" strokeWidth="2" />

        {/* 数据点 */}
        {points.map((p, index) => (
          <circle key={index} cx={p.x} cy={p.y} r="3" fill="currentColor" className="fill-primary" />
        ))}
      </svg>

      {/* 标签 */}
      {points.map((p, index) => {
        const labelRadius = maxRadius * 1.2;
        const labelX = center + labelRadius * Math.cos(p.angle);
        const labelY = center + labelRadius * Math.sin(p.angle);

        return (
          <div
            key={index}
            className="absolute text-xs font-medium text-foreground"
            style={{
              left: `${labelX}px`,
              top: `${labelY}px`,
              transform: 'translate(-50%, -50%)',
              whiteSpace: 'nowrap',
            }}
          >
            <div className="flex flex-col items-center gap-1">
              <span>{p.label}</span>
              <span className="text-primary font-semibold">{(p.value * 100).toFixed(0)}%</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
