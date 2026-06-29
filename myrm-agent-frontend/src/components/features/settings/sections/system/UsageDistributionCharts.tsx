'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';

export const WeekDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
  const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const values = weekDays.map((_, idx) => data[idx.toString()] || data[idx] || 0);
  const maxValue = Math.max(...values, 1);

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <div className="relative h-full flex items-end gap-2 px-2">
            {values.map((val, idx) => {
              const heightPercent = (val / maxValue) * 100;
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${heightPercent}%` }}
                    transition={{ duration: 0.5, delay: idx * 0.05 }}
                    className="w-full rounded-t bg-primary/85 hover:bg-primary transition-colors"
                    title={`${weekDays[idx]}: ${val} tool calls`}
                  />
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex gap-2 px-2 mt-2">
          {weekDays.map((day, idx) => (
            <div key={idx} className="flex-1 text-center text-[10px] text-muted-foreground font-medium">
              {day}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
WeekDistributionChart.displayName = 'WeekDistributionChart';

export const ActivityDailyChart = memo<{ data: Array<{ date: string; tool_calls: number }> }>(({ data }) => {
  if (!data || data.length === 0) return null;

  const maxValue = Math.max(...data.map((d) => d.tool_calls), 1);
  const labels = data.map((d) => {
    const date = new Date(d.date);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  });

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <div className="relative h-full flex items-end gap-1 px-2">
            {data.map((item, idx) => {
              const heightPercent = (item.tool_calls / maxValue) * 100;
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${heightPercent}%` }}
                    transition={{ duration: 0.5, delay: idx * 0.03 }}
                    className="w-full rounded-t bg-primary/85 hover:bg-primary transition-colors"
                    title={`${item.date}: ${item.tool_calls} tool calls`}
                  />
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex gap-1 px-2 mt-2">
          {labels.map((label, idx) => (
            <div key={idx} className="flex-1 text-center text-[9px] text-muted-foreground font-medium">
              {label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
ActivityDailyChart.displayName = 'ActivityDailyChart';

export const HourDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const values = hours.map((h) => data[h] || 0);
  const maxValue = Math.max(...values, 1);

  const points = values
    .map((val, idx) => {
      const x = (idx / 23) * 100;
      const y = 100 - (val / maxValue) * 100;
      return `${x},${y}`;
    })
    .join(' ');

  const pathD = `M 0,100 L ${points} L 100,100 Z`;

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <motion.path
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1 }}
              d={pathD}
              fill="url(#gradient)"
              stroke="rgb(var(--primary))"
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
            <defs>
              <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgb(var(--primary))" stopOpacity="0.3" />
                <stop offset="100%" stopColor="rgb(var(--primary))" stopOpacity="0.05" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div className="flex justify-between px-2 mt-2 text-[10px] text-muted-foreground font-medium">
          <span>00:00</span>
          <span>06:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>23:00</span>
        </div>
      </div>
    </div>
  );
});
HourDistributionChart.displayName = 'HourDistributionChart';
