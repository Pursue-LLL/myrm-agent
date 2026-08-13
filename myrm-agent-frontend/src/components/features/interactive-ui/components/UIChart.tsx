/**
 * UI 图表组件
 * 支持基础的柱状图、折线图、饼图
 */

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

type ChartType = 'bar' | 'line' | 'pie' | 'donut';

interface ChartDataItem {
  label: string;
  value: number;
  color?: string;
}

// 默认颜色调色板
const defaultColors = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#84cc16', // lime
];

export const UIChart: React.FC<UIComponentProps> = ({ props, bindings, data }) => {
  const t = useTranslations('interactiveUI.chart');

  const title = (props.title as string) || '';
  const chartType = (props.type as ChartType) || 'bar';
  const height = (props.height as number) || 200;
  const className = (props.className as string) || '';
  const showLegend = props.showLegend !== false;
  const showValues = props.showValues !== false;

  // 从数据模型获取图表数据
  const dataPath = bindings.data || bindings.value;
  const chartData = useMemo(() => {
    const rawData = dataPath ? getValueByPath(data, dataPath) : props.data;
    if (!rawData || !Array.isArray(rawData)) {return [];}
    return (rawData as ChartDataItem[]).map((item, index) => ({
      ...item,
      color: item.color || defaultColors[index % defaultColors.length],
    }));
  }, [dataPath, data, props.data]);

  // 计算总值和最大值
  const { totalValue, maxValue } = useMemo(() => {
    const total = chartData.reduce((sum, item) => sum + item.value, 0);
    const max = Math.max(...chartData.map((item) => item.value), 1);
    return { totalValue: total, maxValue: max };
  }, [chartData]);

  if (chartData.length === 0) {
    return (
      <div className={cn('flex items-center justify-center p-8 text-gray-400 dark:text-gray-500', className)}>
        <p className="text-sm">{t('noData')}</p>
      </div>
    );
  }

  // 渲染柱状图
  const renderBarChart = () => (
    <div className="flex items-end gap-2 h-full" style={{ height }}>
      {chartData.map((item, index) => {
        const barHeight = (item.value / maxValue) * 100;
        return (
          <div key={index} className="flex-1 flex flex-col items-center gap-1">
            <div className="w-full flex flex-col items-center flex-1 justify-end">
              {showValues && <span className="text-xs text-gray-600 dark:text-gray-400 mb-1">{item.value}</span>}
              <div
                className="w-full rounded-t-md transition-all duration-500 ease-out"
                style={{
                  height: `${barHeight}%`,
                  backgroundColor: item.color,
                  minHeight: '4px',
                }}
              />
            </div>
            <span className="text-xs text-gray-600 dark:text-gray-400 truncate max-w-full text-center">
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );

  // 渲染折线图（SVG 折线 + HTML 数据点，避免 viewBox 拉伸导致圆形变形）
  const renderLineChart = () => {
    const svgW = 1000;
    const svgH = height - 40;
    const points = chartData.map((item, index) => {
      const x = (index / (chartData.length - 1 || 1)) * svgW;
      const y = (1 - item.value / maxValue) * svgH;
      const xPct = (index / (chartData.length - 1 || 1)) * 100;
      const yPct = (1 - item.value / maxValue) * 100;
      return { x, y, xPct, yPct, ...item };
    });

    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

    return (
      <div className="relative" style={{ height }}>
        <div className="relative" style={{ height: svgH }}>
          <svg
            viewBox={`0 0 ${svgW} ${svgH}`}
            className="absolute inset-0 w-full h-full"
            preserveAspectRatio="none"
          >
            {/* 网格线 */}
            {[0, 25, 50, 75, 100].map((pct) => (
              <line
                key={pct}
                x1="0"
                y1={(pct / 100) * svgH}
                x2={svgW}
                y2={(pct / 100) * svgH}
                stroke="currentColor"
                strokeOpacity="0.1"
                strokeWidth="0.5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {/* 折线 */}
            <path
              d={pathD}
              fill="none"
              stroke={defaultColors[0]}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          {/* 数据点使用 HTML 定位，不受 SVG viewBox 拉伸影响 */}
          {points.map((p, i) => (
            <div
              key={i}
              className="absolute rounded-full -translate-x-1/2 -translate-y-1/2"
              style={{
                left: `${p.xPct}%`,
                top: `${p.yPct}%`,
                width: 8,
                height: 8,
                backgroundColor: defaultColors[0],
              }}
            />
          ))}
        </div>
        {/* X 轴标签 */}
        <div className="flex justify-between mt-2">
          {chartData.map((item, index) => (
            <span key={index} className="text-xs text-gray-600 dark:text-gray-400 truncate">
              {item.label}
            </span>
          ))}
        </div>
      </div>
    );
  };

  // 渲染饼图/环形图
  const renderPieChart = () => {
    if (totalValue === 0) {
      return (
        <div className="flex items-center justify-center p-8 text-gray-400 dark:text-gray-500">
          <p className="text-sm">{t('allZero')}</p>
        </div>
      );
    }

    const isDonut = chartType === 'donut';
    const size = Math.min(height, 200);
    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size / 2 - 10;
    const innerRadius = isDonut ? radius * 0.6 : 0;

    let currentAngle = -90; // 从顶部开始

    const slices = chartData.map((item) => {
      const sliceAngle = (item.value / totalValue) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + sliceAngle;
      currentAngle = endAngle;

      const startRad = (startAngle * Math.PI) / 180;
      const endRad = (endAngle * Math.PI) / 180;

      const x1 = centerX + radius * Math.cos(startRad);
      const y1 = centerY + radius * Math.sin(startRad);
      const x2 = centerX + radius * Math.cos(endRad);
      const y2 = centerY + radius * Math.sin(endRad);

      const innerX1 = centerX + innerRadius * Math.cos(startRad);
      const innerY1 = centerY + innerRadius * Math.sin(startRad);
      const innerX2 = centerX + innerRadius * Math.cos(endRad);
      const innerY2 = centerY + innerRadius * Math.sin(endRad);

      const largeArcFlag = sliceAngle > 180 ? 1 : 0;

      const pathD = isDonut
        ? `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2} L ${innerX2} ${innerY2} A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 0 ${innerX1} ${innerY1} Z`
        : `M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2} Z`;

      return {
        ...item,
        pathD,
        percentage: ((item.value / totalValue) * 100).toFixed(1),
      };
    });

    return (
      <div className="flex items-center gap-4">
        <svg width={size} height={size} className="flex-shrink-0">
          {slices.map((slice, index) => (
            <path
              key={index}
              d={slice.pathD}
              fill={slice.color}
              stroke="white"
              strokeWidth="1"
              className="transition-all duration-300 hover:opacity-80"
            />
          ))}
        </svg>
        {showLegend && (
          <div className="flex flex-col gap-2 flex-1">
            {chartData.map((item, index) => (
              <div key={index} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: item.color }} />
                <span className="text-xs text-gray-700 dark:text-gray-300 truncate flex-1">{item.label}</span>
                {showValues && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {item.value} ({slices[index]?.percentage}%)
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={cn('p-4 rounded-lg bg-white dark:bg-gray-800/50', className)}>
      {title && <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-4">{title}</h4>}
      {chartType === 'bar' && renderBarChart()}
      {chartType === 'line' && renderLineChart()}
      {(chartType === 'pie' || chartType === 'donut') && renderPieChart()}
    </div>
  );
};
