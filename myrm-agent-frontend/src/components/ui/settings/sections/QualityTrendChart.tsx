'use client';

import { useMemo } from 'react';

interface TrendDataPoint {
  timestamp: string;
  overall_score: number;
  [key: string]: any;
}

interface TrendChartProps {
  data: TrendDataPoint[];
  width?: number;
  height?: number;
}

/**
 * Skill质量趋势图（纯SVG实现）
 *
 * 展示质量评分随时间的变化趋势
 */
export function QualityTrendChart({ data, width = 600, height = 300 }: TrendChartProps) {
  const padding = { top: 20, right: 30, bottom: 40, left: 50 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const { points, xLabels, yLabels } = useMemo(() => {
    if (data.length === 0) {
      return { points: [], xLabels: [], yLabels: [], minScore: 0, maxScore: 1 };
    }

    const scores = data.map((d) => d.overall_score);
    const minScore = Math.max(0, Math.min(...scores) - 0.1);
    const maxScore = Math.min(1, Math.max(...scores) + 0.1);
    const scoreRange = maxScore - minScore;

    const points = data.map((d, index) => {
      const x = padding.left + (chartWidth / (data.length - 1 || 1)) * index;
      const y = padding.top + chartHeight - ((d.overall_score - minScore) / scoreRange) * chartHeight;
      return { x, y, data: d };
    });

    const xLabels = data.map((d, index) => {
      const date = new Date(d.timestamp);
      const x = padding.left + (chartWidth / (data.length - 1 || 1)) * index;
      return {
        x,
        label: date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
      };
    });

    const yLabels = Array.from({ length: 5 }, (_, i) => {
      const value = minScore + (scoreRange / 4) * i;
      const y = padding.top + chartHeight - ((value - minScore) / scoreRange) * chartHeight;
      return { y, label: (value * 100).toFixed(0) + '%' };
    });

    return { points, xLabels, yLabels, minScore, maxScore };
  }, [data, chartWidth, chartHeight, padding]);

  const pathData = useMemo(() => {
    if (points.length === 0) return '';
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ');
  }, [points]);

  const areaData = useMemo(() => {
    if (points.length === 0) return '';
    const bottom = padding.top + chartHeight;
    const start = `M ${points[0].x},${bottom}`;
    const line = points.map((p) => `L ${p.x},${p.y}`).join(' ');
    const end = `L ${points[points.length - 1].x},${bottom} Z`;
    return start + line + end;
  }, [points, chartHeight, padding]);

  return (
    <div className="relative" style={{ width, height }}>
      <svg width={width} height={height}>
        {/* Y轴网格线 */}
        {yLabels.map((label, index) => (
          <g key={index}>
            <line
              x1={padding.left}
              y1={label.y}
              x2={padding.left + chartWidth}
              y2={label.y}
              stroke="currentColor"
              strokeWidth="0.5"
              className="text-muted-foreground/20"
              strokeDasharray="4 4"
            />
            <text
              x={padding.left - 10}
              y={label.y}
              textAnchor="end"
              dominantBaseline="middle"
              className="text-xs fill-muted-foreground"
            >
              {label.label}
            </text>
          </g>
        ))}

        {/* X轴 */}
        <line
          x1={padding.left}
          y1={padding.top + chartHeight}
          x2={padding.left + chartWidth}
          y2={padding.top + chartHeight}
          stroke="currentColor"
          className="text-muted-foreground/50"
          strokeWidth="1"
        />

        {/* Y轴 */}
        <line
          x1={padding.left}
          y1={padding.top}
          x2={padding.left}
          y2={padding.top + chartHeight}
          stroke="currentColor"
          className="text-muted-foreground/50"
          strokeWidth="1"
        />

        {/* 面积填充 */}
        <path d={areaData} fill="currentColor" className="fill-primary/20" />

        {/* 趋势线 */}
        <path d={pathData} fill="none" stroke="currentColor" strokeWidth="2" className="stroke-primary" />

        {/* 数据点 */}
        {points.map((p, index) => (
          <g key={index}>
            <circle cx={p.x} cy={p.y} r="4" fill="currentColor" className="fill-primary" />
            <title>
              {new Date(p.data.timestamp).toLocaleString('zh-CN')}
              {'\n'}
              Score: {(p.data.overall_score * 100).toFixed(1)}%
            </title>
          </g>
        ))}

        {/* X轴标签 */}
        {xLabels.map((label, index) => (
          <text
            key={index}
            x={label.x}
            y={padding.top + chartHeight + 20}
            textAnchor="middle"
            className="text-xs fill-muted-foreground"
          >
            {label.label}
          </text>
        ))}
      </svg>

      {/* 图表标题 */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 text-sm font-semibold text-foreground">
        Quality Score Trend
      </div>

      {/* Y轴标签 */}
      <div className="absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 -rotate-90 text-sm font-medium text-muted-foreground">
        Overall Score
      </div>
    </div>
  );
}
