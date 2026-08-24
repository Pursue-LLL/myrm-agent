'use client';

/**
 * [INPUT]
 * - @/services/statistics::getLearningLoopStatus (POS: 闭环学习五环状态服务)
 * - @/components/primitives/button::Button (POS: 基础按钮)
 * - next/navigation::useRouter (POS: 路由跳转)
 *
 * [OUTPUT]
 * - GrowingLoopDiscoveryChip: EmptyChat「越用越懂」五环自进化发现胶囊芯片。
 *
 * [POS]
 * 空聊天界面心智发现组件。告知用户 Agent 正在跨会话自省、提炼与进化，提供直达 /journey 的入口。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Sparkles, ArrowRight, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { getLearningLoopStatus, type LearningLoopFiveRingStatusResponse } from '@/services/statistics';

interface GrowingLoopDiscoveryChipProps {
  className?: string;
}

export const GrowingLoopDiscoveryChip = memo(function GrowingLoopDiscoveryChip({
  className,
}: GrowingLoopDiscoveryChipProps) {
  const t = useTranslations('growthDashboard.learningLoop.discoveryChip');
  const router = useRouter();
  const [data, setData] = useState<LearningLoopFiveRingStatusResponse | null>(null);

  useEffect(() => {
    let active = true;
    getLearningLoopStatus(30)
      .then((res) => {
        if (active) {
          setData(res);
        }
      })
      .catch(() => {
        // Soft fail for discovery chip
      });
    return () => {
      active = false;
    };
  }, []);

  const handleNavigate = useCallback(() => {
    router.push('/journey');
  }, [router]);

  if (!data) {
    return null;
  }

  const memoriesCount = data.ring4_consolidation.total_memories;
  const skillsCount = data.ring2_distillation.total_active_skills;

  return (
    <div
      onClick={handleNavigate}
      className={cn(
        'group flex items-center justify-between gap-3 px-3.5 py-2 rounded-full border cursor-pointer select-none transition-all duration-200',
        'bg-background/80 hover:bg-accent/50 border-primary/20 hover:border-primary/40 shadow-xs hover:shadow-sm backdrop-blur-md',
        'max-w-screen-md mx-auto',
        className,
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <div className="p-1 rounded-full bg-primary/10 text-primary shrink-0">
          <Sparkles className="h-3.5 w-3.5 animate-pulse text-primary" />
        </div>
        <div className="flex items-center gap-2 truncate text-xs">
          <span className="font-semibold text-foreground truncate">{t('growsWithYou')}</span>
          <span className="hidden sm:inline text-muted-foreground font-normal truncate">
            · {t('stats', { memories: memoriesCount, skills: skillsCount })}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1 text-[11px] font-medium text-primary shrink-0 group-hover:translate-x-0.5 transition-transform">
        <span>{t('viewLoop')}</span>
        <ArrowRight className="h-3 w-3" />
      </div>
    </div>
  );
});

export default GrowingLoopDiscoveryChip;
