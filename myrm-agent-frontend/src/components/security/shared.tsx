'use client';

import type { LucideIcon } from 'lucide-react';

export const SeverityBadge = ({ severity }: { severity: string }) => {
  const colors = {
    critical: 'bg-red-500/10 text-red-500 border-red-500/20',
    high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  };

  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded border ${colors[severity as keyof typeof colors] || colors.low}`}
    >
      {severity.toUpperCase()}
    </span>
  );
};

export const MetricCard = ({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: number;
  icon: LucideIcon;
  color: string;
}) => (
  <div className={`rounded-lg border p-4 ${color}`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-muted-foreground">{title}</p>
        <p className="text-3xl font-bold mt-1">{value}</p>
      </div>
      <Icon className="w-8 h-8 opacity-50" />
    </div>
  </div>
);
