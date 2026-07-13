'use client';

/**
 * [INPUT] store/config/providerTypes::BuiltInProviderId (POS: 内置 LLM Provider ID 枚举)
 * [OUTPUT] LLM_PROVIDER_BRAND_ICONS: 内置 Provider 品牌图标映射
 * [POS] model-service 层本地 SVG 品牌图标，供 ProviderIcon 渲染，无第三方图标库依赖。
 */

import { memo, type FC, type ReactNode } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { BuiltInProviderId } from '@/store/config/providerTypes';

export interface LlmBrandIconProps {
  size?: number;
  className?: string;
}

type BrandIconComponent = FC<LlmBrandIconProps>;

interface SvgBrandIconProps extends LlmBrandIconProps {
  viewBox?: string;
  children: ReactNode;
}

const SvgBrandIcon = memo<SvgBrandIconProps>(({ size = 20, className, viewBox = '0 0 24 24', children }) => (
  <svg
    width={size}
    height={size}
    viewBox={viewBox}
    className={cn('shrink-0', className)}
    aria-hidden="true"
    role="img"
  >
    {children}
  </svg>
));
SvgBrandIcon.displayName = 'SvgBrandIcon';

function badgeIcon(label: string, bg: string, fg = '#ffffff'): BrandIconComponent {
  const Badge = memo<LlmBrandIconProps>(({ size = 20, className }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" className={cn('shrink-0', className)} aria-hidden="true">
      <rect width="24" height="24" rx="6" fill={bg} />
      <text
        x="12"
        y="12"
        textAnchor="middle"
        dominantBaseline="central"
        fill={fg}
        fontSize={label.length > 2 ? '7' : '9'}
        fontWeight="700"
        fontFamily="system-ui, sans-serif"
      >
        {label}
      </text>
    </svg>
  ));
  Badge.displayName = `BadgeIcon(${label})`;
  return Badge;
}

const OpenAIIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path
      fill="#10A37F"
      d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073ZM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494ZM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646ZM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872Zm16.597 3.855-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667Zm2.01-3.023-.141-.085-4.774-2.781a.776.776 0 0 0-.785 0L8.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66Zm-12.64 4.135-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08-4.778 2.758a.795.795 0 0 0-.393.681l-.004 6.748Zm1.1-2.365 2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5-.005-2.999Z"
    />
  </SvgBrandIcon>
));
OpenAIIcon.displayName = 'OpenAIIcon';

const AnthropicIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path
      fill="#191919"
      className="dark:fill-[#d4d4d4]"
      d="M17.304 3.541h-3.672l6.696 16.918h3.672L17.304 3.541Zm-10.608 0L0 20.459h3.744l1.372-3.55h7.004l1.372 3.55h3.744L10.464 3.541H6.696Zm-.216 10.118 2.436-6.308 2.436 6.308H6.48Z"
    />
  </SvgBrandIcon>
));
AnthropicIcon.displayName = 'AnthropicIcon';

const GeminiIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path fill="#4285F4" d="M12 2 4 6v12l8 4 8-4V6l-8-4Z" />
    <path fill="#34A853" d="m12 2 8 4-3 1.5L12 5 7 7.5 4 6l8-4Z" />
    <path fill="#FBBC05" d="M20 6v12l-3-1.5V7.5L20 6Z" />
    <path fill="#EA4335" d="M4 6v12l8 4V10L4 6Z" />
  </SvgBrandIcon>
));
GeminiIcon.displayName = 'GeminiIcon';

const DeepSeekIcon = badgeIcon('DS', '#4D6BFE');
const OpenRouterIcon = badgeIcon('OR', '#6366F1');
const OllamaIcon = badgeIcon('OL', '#1F2937');
const GroqIcon = badgeIcon('GQ', '#F55036');
const QwenIcon = badgeIcon('QW', '#615CED');
const MoonshotIcon = badgeIcon('MS', '#111827');
const ZhipuIcon = badgeIcon('ZP', '#2563EB');
const LmStudioIcon = badgeIcon('LM', '#0EA5E9');
const XaiIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <rect width="24" height="24" rx="6" fill="#111827" />
    <path
      fill="#f5f5f5"
      d="M7.2 7.2 12 13.1l4.8-5.9h2.1L13.4 15l5.5 6.8h-2.1L12 16.3l-4.8 5.5H5.1l5.5-6.5L5 7.2h2.2Z"
    />
  </SvgBrandIcon>
));
XaiIcon.displayName = 'XaiIcon';
const MinimaxIcon = badgeIcon('MM', '#7C3AED');
const MistralIcon = badgeIcon('MI', '#F97316');
const TogetherIcon = badgeIcon('TG', '#0F766E');
const SiliconCloudIcon = badgeIcon('SC', '#059669');
const DoubaoIcon = badgeIcon('DB', '#2563EB');
const FireworksIcon = badgeIcon('FW', '#7C2D12');
const AzureIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path fill="#0089D6" d="M5.5 4.5h8.2L19.5 14H11L5.5 4.5Z" />
    <path fill="#50E6FF" d="M11 14h8.5L14.5 19.5H6L11 14Z" />
  </SvgBrandIcon>
));
AzureIcon.displayName = 'AzureIcon';

const SparkIcon = badgeIcon('XF', '#E11D48');
const PerplexityIcon = badgeIcon('PX', '#20B8CD');
const JinaIcon = badgeIcon('JN', '#111827', '#f5f5f5');
const BedrockIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path
      fill="#FF9900"
      d="M13.5 3 8 12h4.5l-1.5 9 7.5-12H14l-.5-6Z"
    />
  </SvgBrandIcon>
));
BedrockIcon.displayName = 'BedrockIcon';

const XiaomiMiMoIcon = badgeIcon('XM', '#FF6900');
const NvidiaIcon = memo<LlmBrandIconProps>(({ size = 20, className }) => (
  <SvgBrandIcon size={size} className={className}>
    <path fill="#76B900" d="M8.5 5.5h7v2.2h-7V5.5Zm0 3.4h7v2.2h-7V8.9Zm0 3.4h7V19h-7v-6.7Z" />
  </SvgBrandIcon>
));
NvidiaIcon.displayName = 'NvidiaIcon';

const Ai302Icon = badgeIcon('302', '#0EA5E9');

export const LLM_PROVIDER_BRAND_ICONS: Record<BuiltInProviderId, BrandIconComponent> = {
  openai: OpenAIIcon,
  anthropic: AnthropicIcon,
  gemini: GeminiIcon,
  deepseek: DeepSeekIcon,
  openrouter: OpenRouterIcon,
  zai: ZhipuIcon,
  xai: XaiIcon,
  ollama: OllamaIcon,
  moonshot: MoonshotIcon,
  lm_studio: LmStudioIcon,
  groq: GroqIcon,
  dashscope: QwenIcon,
  minimax: MinimaxIcon,
  mistral: MistralIcon,
  together_ai: TogetherIcon,
  siliconflow: SiliconCloudIcon,
  volcengine: DoubaoIcon,
  fireworks_ai: FireworksIcon,
  azure: AzureIcon,
  spark: SparkIcon,
  perplexity: PerplexityIcon,
  jina_ai: JinaIcon,
  bedrock: BedrockIcon,
  xiaomi_mimo: XiaomiMiMoIcon,
  nvidia: NvidiaIcon,
  ai302: Ai302Icon,
};
