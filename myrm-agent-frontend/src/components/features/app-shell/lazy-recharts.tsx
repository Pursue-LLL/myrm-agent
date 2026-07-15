'use client';

import dynamic from 'next/dynamic';
import type { ComponentType } from 'react';

type RechartsExport = keyof typeof import('recharts');

function lazyRechartsComponent(name: RechartsExport): ComponentType<object> {
  return dynamic(
    () => import('recharts').then((mod) => mod[name] as ComponentType<object>),
    { ssr: false }
  );
}

export const Area = lazyRechartsComponent('Area');
export const AreaChart = lazyRechartsComponent('AreaChart');
export const Bar = lazyRechartsComponent('Bar');
export const BarChart = lazyRechartsComponent('BarChart');
export const CartesianGrid = lazyRechartsComponent('CartesianGrid');
export const Cell = lazyRechartsComponent('Cell');
export const Legend = lazyRechartsComponent('Legend');
export const Line = lazyRechartsComponent('Line');
export const LineChart = lazyRechartsComponent('LineChart');
export const Pie = lazyRechartsComponent('Pie');
export const PieChart = lazyRechartsComponent('PieChart');
export const PolarAngleAxis = lazyRechartsComponent('PolarAngleAxis');
export const PolarGrid = lazyRechartsComponent('PolarGrid');
export const Radar = lazyRechartsComponent('Radar');
export const RadarChart = lazyRechartsComponent('RadarChart');
export const ResponsiveContainer = lazyRechartsComponent('ResponsiveContainer');
export const Tooltip = lazyRechartsComponent('Tooltip');
export const XAxis = lazyRechartsComponent('XAxis');
export const YAxis = lazyRechartsComponent('YAxis');
