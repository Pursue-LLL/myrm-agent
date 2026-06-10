'use client';

/**
 * [INPUT]
 * @/store/chat/types::Message.sessionRecording (POS: 持久化与渲染用的聊天消息实体)
 *
 * [OUTPUT]
 * SessionRecordingCard: 会话录制 WebM 视频内嵌播放器卡片。
 *
 * [POS]
 * 消息内嵌视频回放组件。当 Agent 浏览器会话录制完成后，渲染 HTML5 video 播放器。
 */

import React from 'react';
import { Video } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface SessionRecordingCardProps {
  filename: string;
  previewUrl: string;
}

const SessionRecordingCard: React.FC<SessionRecordingCardProps> = ({ filename, previewUrl }) => {
  const t = useTranslations('chat');

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/30 p-3 max-w-md">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Video className="w-3.5 h-3.5" />
        <span>{t('sessionRecording.label')}</span>
      </div>
      <video
        className="w-full rounded-md"
        src={previewUrl}
        controls
        preload="metadata"
        aria-label={filename}
      />
      <span className="text-xs text-muted-foreground truncate">{filename}</span>
    </div>
  );
};

export default SessionRecordingCard;
