'use client';

/**
 * [INPUT] llm-provider-icons::LLM_PROVIDER_BRAND_ICONS (POS: 内置 Provider 品牌图标)
 * [OUTPUT] ProviderIcon: 内置/自定义 Provider 头像组件
 * [POS] model-service 统一 Provider 头像：设置页列表、模型选择器、智能体能力面板、默认模型选择。
 */

import { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { BUILT_IN_PROVIDERS, type BuiltInProviderId } from '@/store/config/providerTypes';
import { LLM_PROVIDER_BRAND_ICONS } from './llm-provider-icons';

interface ProviderIconProps {
  providerId: string;
  providerName?: string;
  size?: number;
  className?: string;
}

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

const isBuiltInProviderId = (providerId: string): providerId is BuiltInProviderId => {
  return (BUILT_IN_PROVIDERS as readonly string[]).includes(providerId);
};

const getStableColorIndex = (name: string): number => {
  return name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % AVATAR_COLORS.length;
};

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
  const BrandIcon = isBuiltInProviderId(providerId) ? LLM_PROVIDER_BRAND_ICONS[providerId] : undefined;

  return (
    <div className={cn('flex items-center justify-center', className)}>
      {BrandIcon ? <BrandIcon size={size} /> : <LetterAvatar name={providerName || providerId} size={size} />}
    </div>
  );
});

ProviderIcon.displayName = 'ProviderIcon';

export default ProviderIcon;
