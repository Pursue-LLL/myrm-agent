'use client';

/**
 * [INPUT]
 * - @/services/memory/core::getMemoryStats (POS: 前端记忆 API 客户端)
 * - next/navigation::useRouter (POS: 路由跳转)
 * - next-intl::useTranslations (POS: 多语言文案)
 * - lucide-react::Sparkles, ArrowRight (POS: 图标)
 * - @/lib/utils/classnameUtils::cn (POS: 类名合并)
 *
 * [OUTPUT]
 * - GrowingLoopDiscoveryChip: EmptyChat「越用越懂」五环自进化发现胶囊芯片。
 *
 * [POS]
 * 空聊天界面心智发现组件。告知用户 Agent 正在跨会话自省、提炼与进化，入口固定渲染并直达 /journey。
 * 记忆数只是锦上添花：静默读取，读到且大于 0 才显示，失败不弹错误提示。
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
    getMemoryStats({ silent: true })
      .then((res) => {
        if (active) {
          setMemoriesCount(res.total_memories);
        }
      })
      .catch(() => {
        // The count is decoration: no error toast, and the entry point stays usable without it.
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
          {/* Two pulses (about 4 s), then still; no motion at all when the system asks for reduced motion. */}
          <Sparkles className="h-3.5 w-3.5 motion-safe:animate-[pulse_2s_cubic-bezier(0.4,0,0.6,1)_2]" />
        </span>
        {/* Below md only the headline and the arrow stay, or long headlines get cut off. The tail is only the loop's
            name: the chip does not know whether this session is incognito or memory is off, so it cannot state a status. */}
        <span className="flex items-center gap-2 truncate text-xs">
          <span className="font-semibold text-foreground truncate">
            {t('growsWithYou')}
            <span className="hidden md:inline"> · {t('loopName')}</span>
          </span>
          {memoriesCount > 0 && (
            <span className="hidden md:inline text-muted-foreground font-normal truncate">
              · {t('memoriesCount', { count: memoriesCount })}
            </span>
          )}
        </span>
      </span>

      <span className="flex items-center gap-1 text-[11px] font-medium text-primary shrink-0 group-hover:translate-x-0.5 transition-transform">
        <span className="sr-only md:not-sr-only">{t('viewLoop')}</span>
        <ArrowRight className="h-3 w-3" />
      </span>
    </button>
  );
});

export default GrowingLoopDiscoveryChip;
