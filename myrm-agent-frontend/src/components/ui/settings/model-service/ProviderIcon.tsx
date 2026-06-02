'use client';

import { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  OpenAI,
  Anthropic,
  Gemini,
  DeepSeek,
  OpenRouter,
  Ollama,
  Groq,
  Qwen,
  Moonshot,
  Zhipu,
  LmStudio,
  XAI,
  Minimax,
  Mistral,
  Together,
  SiliconCloud,
  Doubao,
  Fireworks,
  Azure,
  Spark,
  Perplexity,
  Jina,
  Bedrock,
  XiaomiMiMo,
  Nvidia,
  Ai302,
} from '@lobehub/icons';
import { BUILT_IN_PROVIDERS } from '@/store/config/providerTypes';

interface ProviderIconProps {
  providerId: string;
  providerName?: string;
  size?: number;
  className?: string;
}

// 头像颜色列表（16种）
const AVATAR_COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-purple-500',
  'bg-orange-500',
  'bg-pink-500',
  'bg-cyan-500',
  'bg-indigo-500',
  'bg-teal-500',
  'bg-rose-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-violet-500',
  'bg-sky-500',
  'bg-lime-500',
  'bg-fuchsia-500',
  'bg-red-500',
];

// 根据名称生成稳定的颜色索引
const getStableColorIndex = (name: string): number => {
  return name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % AVATAR_COLORS.length;
};

// 首字母头像组件
const LetterAvatar = memo<{ name: string; size: number }>(({ name, size }) => {
  const safeName = name || '?';
  const firstLetter = safeName.charAt(0).toUpperCase();
  const colorIndex = getStableColorIndex(safeName);
  const bgColor = AVATAR_COLORS[colorIndex];

  return (
    <div
      className={cn('flex items-center justify-center rounded-md text-white font-semibold', bgColor)}
      style={{ width: size, height: size, fontSize: size * 0.5 }}
    >
      {firstLetter}
    </div>
  );
});

LetterAvatar.displayName = 'LetterAvatar';

const ProviderIcon = memo<ProviderIconProps>(({ providerId, providerName, size = 20, className }) => {
  const renderIcon = () => {
    // 检查是否为内置提供商
    const isBuiltIn = (BUILT_IN_PROVIDERS as readonly string[]).includes(providerId);

    if (isBuiltIn) {
      switch (providerId) {
        case 'openai':
          return <OpenAI size={size} />;
        case 'anthropic':
          return <Anthropic size={size} />;
        case 'gemini':
          return <Gemini.Color size={size} />;
        case 'deepseek':
          return <DeepSeek.Color size={size} />;
        case 'openrouter':
          return <OpenRouter size={size} />;
        case 'ollama':
          return <Ollama size={size} />;
        case 'xai':
          return <XAI size={size} />;
        case 'zai':
          return <Zhipu.Color size={size} />;
        case 'moonshot':
          return <Moonshot size={size} />;
        case 'lm_studio':
          return <LmStudio size={size} />;
        case 'groq':
          return <Groq size={size} />;
        case 'dashscope':
          return <Qwen.Color size={size} />;
        case 'minimax':
          return <Minimax size={size} />;
        case 'mistral':
          return <Mistral.Color size={size} />;
        case 'together_ai':
          return <Together.Color size={size} />;
        case 'siliconflow':
          return <SiliconCloud.Color size={size} />;
        case 'volcengine':
          return <Doubao.Color size={size} />;
        case 'fireworks_ai':
          return <Fireworks.Color size={size} />;
        case 'azure':
          return <Azure.Color size={size} />;
        case 'spark':
          return <Spark.Color size={size} />;
        case 'perplexity':
          return <Perplexity.Color size={size} />;
        case 'jina_ai':
          return <Jina.Avatar size={size} />;
        case 'bedrock':
          return <Bedrock.Color size={size} />;
        case 'xiaomi_mimo':
          return <XiaomiMiMo size={size} />;
        case 'nvidia':
          return <Nvidia.Color size={size} />;
        case 'ai302':
          return <Ai302.Color size={size} />;
        default:
          return <LetterAvatar name={providerName || providerId} size={size} />;
      }
    }

    // 自定义提供商使用首字母头像（基于名称的稳定颜色）
    return <LetterAvatar name={providerName || providerId} size={size} />;
  };

  return <div className={cn('flex items-center justify-center', className)}>{renderIcon()}</div>;
});

ProviderIcon.displayName = 'ProviderIcon';

export default ProviderIcon;
