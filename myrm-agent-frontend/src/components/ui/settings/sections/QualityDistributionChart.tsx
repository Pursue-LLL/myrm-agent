'use client';

import { useTranslations } from 'next-intl';

interface QualityDistributionChartProps {
  excellent: number;
  good: number;
  poor: number;
}

export function QualityDistributionChart({ excellent, good, poor }: QualityDistributionChartProps) {
  const t = useTranslations('settings.skillAggregation');

  const total = excellent + good + poor;

  if (total === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">{t('noData')}</div>;
  }

  const excellentPct = (excellent / total) * 100;
  const goodPct = (good / total) * 100;
  const poorPct = (poor / total) * 100;

  const centerX = 120;
  const centerY = 120;
  const radius = 80;

  const createArc = (startAngle: number, endAngle: number) => {
    const start = polarToCartesian(centerX, centerY, radius, endAngle);
    const end = polarToCartesian(centerX, centerY, radius, startAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    return [
      'M',
      start.x,
      start.y,
      'A',
      radius,
      radius,
      0,
      largeArcFlag,
      0,
      end.x,
      end.y,
      'L',
      centerX,
      centerY,
      'Z',
    ].join(' ');
  };

  const polarToCartesian = (cx: number, cy: number, r: number, angleInDegrees: number) => {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
    return {
      x: cx + r * Math.cos(angleInRadians),
      y: cy + r * Math.sin(angleInRadians),
    };
  };

  let currentAngle = 0;

  const excellentAngle = (excellentPct / 100) * 360;
  const goodAngle = (goodPct / 100) * 360;
  const poorAngle = (poorPct / 100) * 360;

  const excellentPath = createArc(currentAngle, currentAngle + excellentAngle);
  currentAngle += excellentAngle;

  const goodPath = createArc(currentAngle, currentAngle + goodAngle);
  currentAngle += goodAngle;

  const poorPath = createArc(currentAngle, currentAngle + poorAngle);

  return (
    <div className="flex flex-col items-center gap-4">
      <svg width="240" height="240" viewBox="0 0 240 240">
        {excellentAngle > 0 && <path d={excellentPath} fill="#10b981" opacity="0.8" />}
        {goodAngle > 0 && <path d={goodPath} fill="#3b82f6" opacity="0.8" />}
        {poorAngle > 0 && <path d={poorPath} fill="#ef4444" opacity="0.8" />}

        <circle cx={centerX} cy={centerY} r={50} fill="white" />

        <text x={centerX} y={centerY - 10} textAnchor="middle" className="text-2xl font-bold fill-current">
          {total}
        </text>
        <text x={centerX} y={centerY + 15} textAnchor="middle" className="text-xs fill-muted-foreground">
          {t('totalSkills')}
        </text>
      </svg>

      <div className="flex flex-wrap justify-center gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span>
            {t('excellent')} ({excellent}, {excellentPct.toFixed(1)}%)
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span>
            {t('good')} ({good}, {goodPct.toFixed(1)}%)
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span>
            {t('poor')} ({poor}, {poorPct.toFixed(1)}%)
          </span>
        </div>
      </div>
    </div>
  );
}
