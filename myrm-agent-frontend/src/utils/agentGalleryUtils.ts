/**
 * AgentGallery 工具函数
 */

import { avatarGradients } from '@/components/ui/chat-window/agent-config-panel/agentGalleryConstants';

/**
 * 根据 avatar_url 解析颜色渐变
 *
 * @param avatarUrl - 头像URL（支持 "gradient:index" 格式）
 * @param fallbackIndex - 降级索引
 * @returns 颜色渐变对象 { from, to }
 */
export const getGradientFromAvatarUrl = (avatarUrl?: string, fallbackIndex: number = 0) => {
  if (avatarUrl?.startsWith('gradient:')) {
    const gradientIndex = parseInt(avatarUrl.replace('gradient:', ''), 10);
    if (!isNaN(gradientIndex) && gradientIndex >= 0 && gradientIndex < avatarGradients.length) {
      return avatarGradients[gradientIndex];
    }
  }
  return avatarGradients[fallbackIndex % avatarGradients.length];
};
