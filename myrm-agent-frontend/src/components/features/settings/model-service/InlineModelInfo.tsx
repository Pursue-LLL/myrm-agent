import { memo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Eye, Wrench, Brain, Headphones, Video, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import useProviderStore from '@/store/useProviderStore';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { formatTokens, formatPrice } from '@/lib/utils/modelFormatUtils';

interface InlineModelInfoProps {
  providerId: string;
  modelName: string;
  isEnabled: boolean;
}

const CapabilityIcon = memo<{ icon: ReactNode; label: string }>(({ icon, label }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <div className="flex items-center justify-center w-5 h-5 rounded bg-[#d7e1e1] dark:bg-primary/15 text-foreground dark:text-primary">
        {icon}
      </div>
    </TooltipTrigger>
    <TooltipContent side="top" className="text-xs">
      {label}
    </TooltipContent>
  </Tooltip>
));
CapabilityIcon.displayName = 'CapabilityIcon';

/**
 * 内联模型信息组件
 * 显示模型支持的能力图标 + 上下文长度 + 价格
 */
export const InlineModelInfo = memo<InlineModelInfoProps>(({ providerId, modelName, isEnabled }) => {
  const t = useTranslations('settings.modelService.modelInfo');
  const modelInfo = useProviderStore((state) => state.customModelInfo[`${providerId}/${modelName}`]);

  if (!modelInfo) return null;

  const {
    supports_vision,
    supports_function_calling,
    supports_reasoning,
    supports_audio_input,
    supports_video_input,
    max_input_tokens,
    input_cost_per_million,
    output_cost_per_million,
  } = modelInfo;

  return (
    <div className={cn('flex items-center gap-1.5 flex-wrap text-xs transition-opacity', !isEnabled && 'opacity-50')}>
      <TooltipProvider>
        {supports_function_calling && (
          <CapabilityIcon icon={<Wrench className="w-3 h-3" />} label={t('functionCalling')} />
        )}
        {supports_vision && <CapabilityIcon icon={<Eye className="w-3 h-3" />} label={t('vision')} />}
        {supports_audio_input && <CapabilityIcon icon={<Headphones className="w-3 h-3" />} label={t('audioInput')} />}
        {supports_video_input && <CapabilityIcon icon={<Video className="w-3 h-3" />} label={t('videoInput')} />}
        {supports_reasoning && <CapabilityIcon icon={<Brain className="w-3 h-3" />} label={t('reasoning')} />}
      </TooltipProvider>

      {max_input_tokens && (
        <span className="text-[10px] text-muted-foreground">
          {t('contextLabel')}: {formatTokens(max_input_tokens)}
        </span>
      )}

      {input_cost_per_million !== undefined && output_cost_per_million !== undefined && (
        <div className="flex items-center gap-1.5 text-[10px]">
          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
            <ChevronDown className="w-2.5 h-2.5" />
            {formatPrice(input_cost_per_million)}
          </span>
          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
            <ChevronUp className="w-2.5 h-2.5" />
            {formatPrice(output_cost_per_million)}
          </span>
        </div>
      )}
    </div>
  );
});

InlineModelInfo.displayName = 'InlineModelInfo';
