import { useMemo } from 'react';
import useChatStore from '@/store/useChatStore';
import { ArtifactVersion } from '@/store/chat/types';

/**
 * 从聊天历史中解析指定 Artifact 的所有版本。
 *
 * 版本来源：
 * 1. Assistant Message 中的 <antArtifact identifier="artifactId">...</antArtifact>
 * 2. User Message 中的 <edited_artifact id="artifactId">...</edited_artifact>
 */
export const useArtifactVersionsFromHistory = (artifactId: string | undefined): ArtifactVersion[] => {
  const messages = useChatStore((state) => state.messages);

  return useMemo(() => {
    if (!artifactId) return [];

    const versions: ArtifactVersion[] = [];
    let versionNumber = 1;

    messages.forEach((msg) => {
      // 1. 检查 Assistant 生成的 Artifacts
      if (msg.role === 'assistant' && msg.artifacts) {
        const artifact = msg.artifacts.find((a) => a.id === artifactId);
        if (artifact) {
          // 注意：Assistant 生成的 Artifact 内容通常通过 URL 获取，
          // 但如果流式输出时我们拦截了内容，或者后续需要支持，这里可以扩展。
          // 目前我们用一个特殊的占位符或依赖组件去 fetch。
          versions.push({
            versionId: `msg-${msg.messageId}-assistant`,
            versionNumber: versionNumber++,
            content: '',
            createdAt: new Date(msg.createdAt).toISOString(),
            description: 'Agent Generated',
            source: 'assistant',
            originalArtifact: artifact,
          });
        }
      }

      // 2. 检查 User 修改的 Artifacts
      if (msg.role === 'user' && msg.content) {
        // 解析 <edited_artifact id="artifactId">...</edited_artifact>
        const regex = new RegExp(`<edited_artifact\\s+id="${artifactId}">([\\s\\S]*?)</edited_artifact>`, 'g');
        let match;
        while ((match = regex.exec(msg.content)) !== null) {
          versions.push({
            versionId: `msg-${msg.messageId}-user`,
            versionNumber: versionNumber++,
            content: match[1].trim(),
            createdAt: new Date(msg.createdAt).toISOString(),
            description: 'User Edited',
            source: 'user',
          });
        }
      }
    });

    return versions;
  }, [messages, artifactId]);
};
