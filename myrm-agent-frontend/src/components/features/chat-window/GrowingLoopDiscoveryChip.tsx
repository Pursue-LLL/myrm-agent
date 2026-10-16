'use client';

/**
 * [INPUT]
 * - @/services/memory/core::getMemoryStats (POS: 记忆总数服务)
 * - next/navigation::useRouter (POS: 路由跳转)
 *
 * [OUTPUT]
 * - GrowingLoopDiscoveryChip: EmptyChat「越用越懂」五环自进化发现胶囊芯片。
 *
 * [POS]
 * 空聊天界面心智发现组件。告知用户 Agent 正在跨会话自省、提炼与进化，提供直达 /journey 的入口。
 * 入口固定渲染，不等任何请求；记忆数只是锦上添花，读到且大于 0 才显示。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Sparkles, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getMemoryStats } from '@/services/memory/core';

interface GrowingLoopDiscoveryChipProps {
  className?: string;
}

export const GrowingLoopDiscoveryChip = memo(function GrowingLoopDiscoveryChip({
  className,
}: GrowingLoopDiscoveryChipProps) {
  const t = useTranslations('growthDashboard.learningLoop.discoveryChip');
  const router = useRouter();
  const [memoriesCount, setMemoriesCount] = useState(0);

  useEffect(() => {
    let active = true;
    getMemoryStats()
      .then((res) => {
        if (active) {
          setMemoriesCount(res.total_memories);
        }
      })
      .catch(() => {
        // The count is decoration; the entry point stays usable without it.
      });
    return () => {
      active = false;
    };
  }, []);

  const handleNavigate = useCallback(() => {
    router.push('/journey');
  }, [router]);

  return (
    <button
      type="button"
      onClick={handleNavigate}
      className={cn(
        'group flex w-full items-center justify-between gap-3 px-3.5 py-2 rounded-full border text-start cursor-pointer select-none transition-all duration-200',
        'bg-background/80 hover:bg-accent/50 border-primary/20 hover:border-primary/40 shadow-xs hover:shadow-sm backdrop-blur-md',
        'max-w-screen-md mx-auto',
        className,
      )}
    >
      <span className="flex items-center gap-2 min-w-0">
        <span className="p-1 rounded-full bg-primary/10 text-primary shrink-0">
          <Sparkles className="h-3.5 w-3.5 animate-pulse text-primary" />
        </span>
        <span className="flex items-center gap-2 truncate text-xs">
          <span className="font-semibold text-foreground truncate">{t('growsWithYou')}</span>
          {memoriesCount > 0 && (
            <span className="hidden sm:inline text-muted-foreground font-normal truncate">
              · {t('memoriesCount', { count: memoriesCount })}
            </span>
          )}
        </span>
      </span>

      <span className="flex items-center gap-1 text-[11px] font-medium text-primary shrink-0 group-hover:translate-x-0.5 transition-transform">
        <span>{t('viewLoop')}</span>
        <ArrowRight className="h-3 w-3" />
      </span>
    </button>
  );
});

export default GrowingLoopDiscoveryChip;
