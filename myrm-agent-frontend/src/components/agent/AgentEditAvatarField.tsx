'use client';

/**
 * [INPUT] ./useAgentAvatarUpload::useAgentAvatarUpload (POS: 头像文件选择与上传), ./agent-icons::AGENT_ICON_REGISTRY, AgentIcon (POS: 内置图标注册表), ./AgentAvatar::AgentAvatar (POS: 头像展示)
 * [OUTPUT] AgentEditAvatarField: 头像预览（点击上传）+ 内置图标网格 + 使用提示
 * [POS] 智能体创建 / 编辑表单的头像区段；已保存的智能体选择文件后即上传，新建时仅保留本地预览。
 */

import { Loader2, Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { AgentIcon, AGENT_ICON_REGISTRY } from '@/components/agent/agent-icons';
import { useAgentAvatarUpload } from '@/components/agent/useAgentAvatarUpload';
import { cn } from '@/lib/utils';
import { activateOnKey } from '@/lib/utils/a11y';

interface AgentEditAvatarFieldProps {
  agentId?: string | null;
  avatarUrl?: string;
  name: string;
  onAvatarChange: (url: string) => void;
}

export function AgentEditAvatarField({ agentId, avatarUrl, name, onAvatarChange }: AgentEditAvatarFieldProps) {
  const t = useTranslations('Agent');
  const { fileInputRef, isUploadingAvatar, handleAvatarClick, handleFileChange } = useAgentAvatarUpload({
    agentId,
    onAvatarChange,
  });

  return (
    <div className="flex flex-col items-center gap-4 mb-6">
      <button
        type="button"
        className="relative group cursor-pointer border-none bg-transparent p-0 m-0 text-left"
        onClick={handleAvatarClick}
        onKeyDown={activateOnKey}
        aria-label={t('avatar.hint')}
      >
        <AgentAvatar
          url={avatarUrl}
          name={name || 'New Agent'}
          size="lg"
          className="h-16 w-16 transition-opacity group-hover:opacity-80"
        />
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40 rounded-xl">
          {isUploadingAvatar ? (
            <Loader2 className="h-5 w-5 animate-spin text-white" />
          ) : (
            <Upload className="h-5 w-5 text-white" />
          )}
        </div>
        <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileChange} />
      </button>
      <div className="flex flex-wrap justify-center gap-1.5 max-w-[280px]">
        {Object.keys(AGENT_ICON_REGISTRY).map((iconId) => (
          <button
            key={iconId}
            type="button"
            className={cn(
              'rounded-lg p-0.5 transition-all hover:scale-110',
              avatarUrl === `icon:${iconId}`
                ? 'ring-2 ring-primary ring-offset-1 ring-offset-background'
                : 'opacity-60 hover:opacity-100',
            )}
            onClick={() => onAvatarChange(`icon:${iconId}`)}
          >
            <AgentIcon iconId={iconId} size="sm" />
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t('avatar.hint')}</p>
    </div>
  );
}
