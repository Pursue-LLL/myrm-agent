/**
 * [INPUT] @/lib/utils/apiConfig::getBackendUrl, @/lib/utils/authHeaders::getAuthHeaders (POS: 后端地址与鉴权头), @/hooks/shared/useToast::toast (POS: 失败提示)
 * [OUTPUT] useAgentAvatarUpload: 头像文件选择与上传（隐藏 file input 的 ref、上传中状态、点击与选择处理）
 * [POS] AgentEditAvatarField 的上传逻辑；选择文件后立即以本地预览 URL 回填，已保存的智能体再上传并回填服务端 URL。
 */

import { useRef, useState, type ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { toast } from '@/hooks/shared/useToast';

interface UseAgentAvatarUploadParams {
  agentId?: string | null;
  onAvatarChange: (url: string) => void;
}

export function useAgentAvatarUpload({ agentId, onAvatarChange }: UseAgentAvatarUploadParams) {
  const t = useTranslations('Agent');
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }

    // Local preview instantly
    const objectUrl = URL.createObjectURL(file);
    onAvatarChange(objectUrl);

    if (!agentId) {
      // A new agent has no id to upload against yet: the local preview URL is kept and does not persist across reloads.
      return;
    }

    setIsUploadingAvatar(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/avatar`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to upload avatar');
      }

      const result = (await response.json()) as { data: { avatar_url: string } };
      onAvatarChange(result.data.avatar_url);
    } catch (error) {
      console.error('Avatar upload failed:', error);
      toast.error(t('avatar.error'));
    } finally {
      setIsUploadingAvatar(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return { fileInputRef, isUploadingAvatar, handleAvatarClick, handleFileChange };
}
