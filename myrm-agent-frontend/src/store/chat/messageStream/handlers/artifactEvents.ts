/**
 * [POS]
 * Chat SSE event handler slice (artifactEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import * as H from "./handlerDeps";

export async function artifactEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.ARTIFACTS) {
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      // 初始化 artifacts 数组
      if (!state.messages[messageIndex].artifacts) {
        state.messages[messageIndex].artifacts = [];
      }

      // 添加 artifacts
      if (Array.isArray(data.data)) {
        state.messages[messageIndex].artifacts!.push(...data.data);

        // 如果 Portal 正在显示 artifact，更新其信息（包括 preview_url）
        const portalStore = H.useArtifactPortalStore.getState();
        const activeTab =
          portalStore.activeTabIndex >= 0 && portalStore.activeTabIndex < portalStore.openTabs.length
            ? portalStore.openTabs[portalStore.activeTabIndex]
            : null;
        if (activeTab) {
          // 检查是否是当前正在预览的 artifact
          const updatedArtifact = data.data.find((a: { id: string }) => a.id === activeTab.artifact?.id);
          if (updatedArtifact) {
            portalStore.updateCurrentArtifact(updatedArtifact);
            // 如果仍在生成中，结束实时预览
            if (activeTab.isGenerating) {
              portalStore.endRealtimePreview();
            }
          }
        }
      }

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  // 处理 artifact 内容实时更新事件（用于实时预览）
  if (data.type === H.AgentEventType.ARTIFACT_CONTENT) {
    const portalStore = H.useArtifactPortalStore.getState();
    const activeTab =
      portalStore.activeTabIndex >= 0 && portalStore.activeTabIndex < portalStore.openTabs.length
        ? portalStore.openTabs[portalStore.activeTabIndex]
        : null;

    // 如果是完整内容（文件创建完成）
    if (data.subtype === 'complete' && data.content) {
      // 创建临时 artifact 对象用于实时预览
      const tempArtifact: Artifact = {
        id: data.artifactId,
        filename: data.filename,
        type: (data.artifactType ?? 'code') as ArtifactType,
        content_type: 'text/plain',
        size: data.content.length,
        preview_url: '',
        download_url: '',
        language: data.language,
      };

      // 自动打开 Portal 并显示内容
      portalStore.startRealtimePreview(tempArtifact);
      portalStore.appendContent(data.content);
      portalStore.endRealtimePreview();
    }

    // 如果是新 artifact 开始生成（流式）
    if (data.subtype === 'start') {
      const artifact = data.artifact;
      if (artifact) {
        portalStore.startRealtimePreview(artifact);
      }
    }

    // 如果是内容增量更新（流式）
    if (data.subtype === 'chunk' && data.content) {
      if (activeTab?.isGenerating && activeTab?.artifact?.id === data.artifactId) {
        portalStore.appendContent(data.content);
      }
    }

    // 如果是生成完成（流式）
    if (data.subtype === 'end') {
      if (activeTab?.isGenerating && activeTab?.artifact?.id === data.artifactId) {
        portalStore.endRealtimePreview();
      }
    }
  }

  // 处理 UI 工件事件
  if (data.type === H.AgentEventType.UI_UPDATE) {
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      if (data.subtype === 'ui_artifact') {
        // 初始化 uiArtifacts 数组
        if (!state.messages[messageIndex].uiArtifacts) {
          state.messages[messageIndex].uiArtifacts = [];
        }

        // 添加 UI artifacts
        if (Array.isArray(data.data)) {
          state.messages[messageIndex].uiArtifacts!.push(...(data.data as H.UIArtifact[]));
        }
      } else if (data.subtype === 'data_update') {
        const payload = data.data;
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
          return;
        }
        const update = payload as { surface_id?: string; updates?: Record<string, unknown> };
        const surfaceId = update.surface_id;
        const updates = update.updates;
        if (!surfaceId || !updates || typeof updates !== 'object') {
          return;
        }
        const artifacts = state.messages[messageIndex].uiArtifacts;
        if (!artifacts) {
          return;
        }
        const artifactIndex = artifacts.findIndex((item) => item.surface_id === surfaceId);
        if (artifactIndex === -1) {
          return;
        }
        const current = artifacts[artifactIndex];
        artifacts[artifactIndex] = {
          ...current,
          data: { ...current.data, ...updates },
        };
      }

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  return null;
}
