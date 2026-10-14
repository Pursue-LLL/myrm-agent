/**
 * [INPUT] next-intl `settings.skills.scanRisk`; @/lib/skills/scanRiskText
 * [OUTPUT] useScanRiskText: 绑定当前语言的扫描文案函数（threat 类别、严重度、待审信号、处置建议）
 * [POS] features/skills 三处扫描结论渲染（成长卡片、本地技能预览、技能详情）共用的翻译入口
 */
'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { riskRemediation, riskSignalLabel, severityLabel, threatTypeLabel } from '@/lib/skills/scanRiskText';

export interface ScanRiskText {
  threatLabel: (threatType: string) => string;
  severityLabel: (severity: string) => string;
  signalLabel: (signal: string) => string;
  remediation: (signals: readonly string[]) => string;
}

export function useScanRiskText(): ScanRiskText {
  const t = useTranslations('settings.skills.scanRisk');
  return useMemo(
    () => ({
      threatLabel: (threatType) => threatTypeLabel(t, threatType),
      severityLabel: (severity) => severityLabel(t, severity),
      signalLabel: (signal) => riskSignalLabel(t, signal),
      remediation: (signals) => riskRemediation(t, signals).join(' '),
    }),
    [t],
  );
}
