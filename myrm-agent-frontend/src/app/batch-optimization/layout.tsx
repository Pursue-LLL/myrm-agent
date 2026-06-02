import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { getLocale } from '@/i18n';
import { selectLocalizedText } from '@/lib/utils/localeText';

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();

  return {
    title: selectLocalizedText('Batch Optimization / 批量优化', locale),
    description: selectLocalizedText(
      'Manage batch skill optimization tasks with real-time progress tracking / 管理批量技能优化任务并实时跟踪进度',
      locale,
    ),
  };
}

export default function BatchOptimizationLayout({ children }: { children: ReactNode }) {
  return children;
}
