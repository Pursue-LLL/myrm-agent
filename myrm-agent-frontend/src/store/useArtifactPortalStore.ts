'use client';

/**
 * [INPUT]
 * `@/store/chat/types`::Artifact（POS: 聊天与工件领域类型）；
 * `@/lib/constants/artifact`（POS: Portal 宽度、缓存 TTL、标签上限等常量）。
 * [OUTPUT]
 * Zustand `useArtifactPortalStore`：`openArtifact`/`addTab` 支持 `OpenArtifactTabOptions`（`lineRange`、`diffPreviewTruncated`）、`updateTabContent` 可将 diff 预览标为截断。
 * [POS]
 * Artifact Portal 全局状态（打开的标签、缓存、协同脏标记、diff 截断语义）。
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { useShallow } from 'zustand/react/shallow';

import { Artifact, ArtifactVersion } from '@/store/chat/types';

/** 空版本数组常量，避免每次创建新引用 */
const EMPTY_VERSIONS: ArtifactVersion[] = [];
import {
  ARTIFACT_CACHE_MAX_SIZE,
  ARTIFACT_CACHE_TTL,
  PORTAL_DEFAULT_WIDTH,
  PORTAL_MIN_WIDTH,
  PORTAL_MAX_WIDTH,
  MAX_VERSIONS_PER_ARTIFACT,
  MAX_OPEN_TABS,
} from '@/lib/constants/artifact';

/** Portal 显示模式 */
export enum ArtifactDisplayMode {
  /** 预览模式 */
  Preview = 'preview',
  /** 代码模式 */
  Code = 'code',
}

/** 错误类型枚举 */
export enum ArtifactErrorType {
  /** 文件不存在 */
  NotFound = 'not_found',
  /** 服务器错误 */
  ServerError = 'server_error',
  /** 网络错误 */
  NetworkError = 'network_error',
  /** 权限错误 */
  PermissionDenied = 'permission_denied',
  /** 内容解析错误 */
  ParseError = 'parse_error',
  /** 未知错误 */
  Unknown = 'unknown',
}

/** 错误信息接口 */
export interface ArtifactError {
  /** 错误类型 */
  type: ArtifactErrorType;
  /** HTTP 状态码（如有） */
  statusCode?: number;
  /** 错误消息 i18n key（如 'errors.notFound'，由 UI 层翻译） */
  messageKey: string;
  /** 消息参数（用于 i18n 插值） */
  messageParams?: Record<string, string | number>;
  /** 详细信息 */
  details?: string;
  /** 是否可重试 */
  retryable: boolean;
}

/** 缓存条目 */
interface CacheEntry {
  content: string;
  timestamp: number;
}

/** 打开的工件标签页 */
export interface OpenArtifactTab {
  artifact: Artifact;
  content: string;
  contentLoading: boolean;
  error: ArtifactError | null;
  isGenerating: boolean;
  displayMode: ArtifactDisplayMode;
  /** 当前查看的版本索引（-1 表示最新版本） */
  viewingVersionIndex: number;
  /** 标签页打开时间戳（用于 LRU 策略） */
  openedAt: number;
  /** 最后访问时间戳（用于最少使用策略） */
  lastAccessedAt: number;
  /** 视图状态：需要滚动到的行号范围 (例如 "10-20") */
  lineRange?: string;
  /** Diff 预览是否为截断快照（SSE `file_diff.truncated`） */
  diffPreviewTruncated?: boolean;
}

/** Portal 核心状态接口（单一真实来源） */
interface ArtifactPortalCoreState {
  /** Portal 是否展开 */
  isOpen: boolean;
  /** 面板宽度 */
  panelWidth: number;
  /** 内容缓存 (artifactId -> content) */
  contentCache: Record<string, CacheEntry>;
  /** 打开的工件标签页列表（核心数据源） */
  openTabs: OpenArtifactTab[];
  /** 当前激活的标签页索引 */
  activeTabIndex: number;
  /** 脏状态的 Artifacts (artifactId -> content) */
  dirtyArtifacts: Record<string, string>;
}

/** 打开 / 新增标签页时的可选配置 */
export interface OpenArtifactTabOptions {
  lineRange?: string;
  diffPreviewTruncated?: boolean;
}

/** Portal 操作接口 */
interface ArtifactPortalActions {
  /** 打开 Portal 并显示指定 Artifact */
  openArtifact: (artifact: Artifact, options?: OpenArtifactTabOptions) => void;
  /** 关闭 Portal */
  closePortal: () => void;
  /** 切换显示模式 */
  setDisplayMode: (mode: ArtifactDisplayMode) => void;
  /** 设置当前 tab 的内容 */
  setContent: (content: string) => void;
  /** 追加内容（用于实时预览） */
  appendContent: (chunk: string) => void;
  /** 设置内容加载状态 */
  setContentLoading: (loading: boolean) => void;
  /** 设置错误信息 */
  setError: (error: ArtifactError | null) => void;
  /** 清除错误 */
  clearError: () => void;
  /** 设置生成状态（用于实时预览） */
  setIsGenerating: (generating: boolean) => void;
  /** 开始实时预览（打开 Portal 并标记为生成中） */
  startRealtimePreview: (artifact: Artifact) => void;
  /** 结束实时预览（标记生成完成） */
  endRealtimePreview: () => void;
  /** 更新当前 Artifact（用于实时预览） */
  updateCurrentArtifact: (artifact: Partial<Artifact>) => void;
  /** 自动切换到预览模式（生成完成后调用） */
  autoSwitchToPreview: () => void;
  /** 设置面板宽度 */
  setPanelWidth: (width: number) => void;
  /** 获取缓存内容 */
  getCachedContent: (artifactId: string) => string | null;
  /** 设置缓存内容 */
  setCachedContent: (artifactId: string, content: string) => void;
  /** 清理过期缓存 */
  cleanupCache: () => void;
  /** 添加新标签页（或激活已存在的） */
  addTab: (artifact: Artifact, options?: OpenArtifactTabOptions) => void;
  /** 关闭指定标签页 */
  closeTab: (index: number) => void;
  /** 切换到指定标签页 */
  switchTab: (index: number) => void;
  /** 关闭其他标签页 */
  closeOtherTabs: (index: number) => void;
  /** 关闭所有标签页 */
  closeAllTabs: () => void;
  /** 更新指定标签页的内容 */
  updateTabContent: (artifactId: string, content: string, options?: { truncated?: boolean }) => void;
  /** 更新指定标签页的加载状态 */
  updateTabLoading: (artifactId: string, loading: boolean) => void;
  /** 更新指定标签页的错误 */
  updateTabError: (artifactId: string, error: ArtifactError | null) => void;
  // ==================== 版本历史 Actions ====================
  /** 创建新版本（保存当前内容为一个版本） */
  createVersion: (description?: string) => void;
  /** 切换到指定版本查看 */
  switchToVersion: (versionIndex: number, content?: string) => void;
  /** 回滚到指定版本（丢弃之后的版本） */
  rollbackToVersion: (versionIndex: number, content?: string) => void;
  /** 获取当前 tab 的版本列表 */
  getVersions: () => Artifact['versions'];
  /** 获取当前查看的版本索引 */
  getViewingVersionIndex: () => number;

  // ==================== 协同编辑 Actions ====================
  /** 标记 Artifact 为脏状态（用户已修改但未同步） */
  markAsDirty: (artifactId: string, content: string) => void;
  /** 清除脏状态标记 */
  clearDirtyState: (artifactId: string) => void;
  /** 获取所有脏状态的 Artifacts */
  getDirtyArtifacts: () => Record<string, string>;
}

/** 根据 HTTP 状态码解析错误类型 */
export function parseErrorFromResponse(statusCode: number, statusText: string, errorBody?: string): ArtifactError {
  let type: ArtifactErrorType;
  let messageKey: string;
  let retryable: boolean;
  let messageParams: Record<string, string | number> | undefined;

  switch (statusCode) {
    case 404:
      type = ArtifactErrorType.NotFound;
      messageKey = 'errors.notFound';
      retryable = false;
      break;
    case 403:
      type = ArtifactErrorType.PermissionDenied;
      messageKey = 'errors.permissionDenied';
      retryable = false;
      break;
    case 500:
    case 502:
    case 503:
    case 504:
      type = ArtifactErrorType.ServerError;
      messageKey = 'errors.serverError';
      retryable = true;
      break;
    default:
      if (statusCode >= 400 && statusCode < 500) {
        type = ArtifactErrorType.Unknown;
        messageKey = 'errors.unknown';
        messageParams = { statusCode };
        retryable = false;
      } else {
        type = ArtifactErrorType.Unknown;
        messageKey = 'errors.unknown';
        messageParams = { statusCode };
        retryable = true;
      }
  }

  return {
    type,
    statusCode,
    messageKey,
    messageParams,
    details: errorBody || statusText,
    retryable,
  };
}

/** 解析网络错误 */
export function parseNetworkError(error: Error): ArtifactError {
  const isNetworkError =
    error.name === 'TypeError' &&
    (error.message.includes('Failed to fetch') ||
      error.message.includes('NetworkError') ||
      error.message.includes('Network request failed'));

  if (isNetworkError) {
    return {
      type: ArtifactErrorType.NetworkError,
      messageKey: 'errors.networkError',
      details: error.message,
      retryable: true,
    };
  }

  return {
    type: ArtifactErrorType.Unknown,
    messageKey: 'errors.unknown',
    details: error.message || error.stack,
    retryable: true,
  };
}

type ArtifactPortalStore = ArtifactPortalCoreState & ArtifactPortalActions;

/** 初始状态 */
const initialCoreState: ArtifactPortalCoreState = {
  isOpen: false,
  panelWidth: PORTAL_DEFAULT_WIDTH,
  contentCache: {},
  openTabs: [],
  activeTabIndex: -1,
  dirtyArtifacts: {},
};

/** 获取当前激活的 tab（辅助函数） */
function getActiveTab(state: ArtifactPortalCoreState): OpenArtifactTab | null {
  if (state.activeTabIndex >= 0 && state.activeTabIndex < state.openTabs.length) {
    return state.openTabs[state.activeTabIndex];
  }
  return null;
}

/** Artifact Portal 状态管理 */
const useArtifactPortalStore = create<ArtifactPortalStore>()(
  immer((set, get) => ({
    ...initialCoreState,

    // ==================== Actions ====================
    openArtifact: (artifact: Artifact, options?: OpenArtifactTabOptions) => {
      get().addTab(artifact, options);
    },

    closePortal: () => {
      get().closeAllTabs();
    },

    setDisplayMode: (mode: ArtifactDisplayMode) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.displayMode = mode;
        }
      });
    },

    setContent: (content: string) => {
      const state = get();
      const currentArtifact = getActiveTab(state)?.artifact;
      if (currentArtifact) {
        state.setCachedContent(currentArtifact.id, content);
      }
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.content = content;
          tab.contentLoading = false;
        }
      });
    },

    appendContent: (chunk: string) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.content += chunk;
          // 实时更新缓存
          state.contentCache[tab.artifact.id] = {
            content: tab.content,
            timestamp: Date.now(),
          };
        }
      });
    },

    setContentLoading: (loading: boolean) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.contentLoading = loading;
        }
      });
    },

    setError: (error: ArtifactError | null) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.error = error;
          if (error) {
            tab.contentLoading = false;
          }
        }
      });
    },

    clearError: () => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.error = null;
        }
      });
    },

    setIsGenerating: (generating: boolean) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.isGenerating = generating;
        }
      });
    },

    startRealtimePreview: (artifact: Artifact) => {
      const now = Date.now();
      set((state) => {
        // 检查是否已存在
        const existingIndex = state.openTabs.findIndex((tab) => tab.artifact.id === artifact.id);

        if (existingIndex >= 0) {
          // 已存在，切换到该标签页并重置状态
          state.activeTabIndex = existingIndex;
          const tab = state.openTabs[existingIndex];
          tab.artifact = artifact;
          // Mermaid should default to Preview, others to Code during generation
          tab.displayMode = artifact.type === 'mermaid' ? ArtifactDisplayMode.Preview : ArtifactDisplayMode.Code;
          tab.content = '';
          tab.contentLoading = false;
          tab.error = null;
          tab.isGenerating = true;
          tab.viewingVersionIndex = -1;
          tab.lastAccessedAt = now;
          tab.diffPreviewTruncated = false;
        } else {
          // 新增标签页
          const newTab: OpenArtifactTab = {
            artifact,
            content: '',
            contentLoading: false,
            error: null,
            isGenerating: true,
            // Mermaid should default to Preview, others to Code during generation
            displayMode: artifact.type === 'mermaid' ? ArtifactDisplayMode.Preview : ArtifactDisplayMode.Code,
            viewingVersionIndex: -1,
            openedAt: now,
            lastAccessedAt: now,
            diffPreviewTruncated: false,
          };
          state.openTabs.push(newTab);
          state.activeTabIndex = state.openTabs.length - 1;
        }
        state.isOpen = true;
      });
    },

    endRealtimePreview: () => {
      const state = get();
      const tab = getActiveTab(state);

      // 缓存最终内容
      if (tab && tab.content) {
        state.setCachedContent(tab.artifact.id, tab.content);
      }

      set((draftState) => {
        const draftTab = getActiveTab(draftState);
        if (draftTab) {
          draftTab.isGenerating = false;
          draftTab.displayMode = ArtifactDisplayMode.Preview;

          // 自动创建版本（当内容有变化时）
          if (draftTab.content) {
            const versions = draftTab.artifact.versions || [];
            const lastVersion = versions[versions.length - 1];

            // 只有当内容与上一个版本不同时才创建新版本
            if (!lastVersion || lastVersion.content !== draftTab.content) {
              if (!draftTab.artifact.versions) {
                draftTab.artifact.versions = [];
              }

              draftTab.artifact.versions.push({
                versionId: `v${Date.now()}`,
                versionNumber: draftTab.artifact.versions.length + 1,
                content: draftTab.content,
                createdAt: new Date().toISOString(),
                description: undefined,
              });

              // 限制版本数量，删除最旧的版本
              while (draftTab.artifact.versions.length > MAX_VERSIONS_PER_ARTIFACT) {
                draftTab.artifact.versions.shift();
              }

              draftTab.artifact.currentVersionIndex = draftTab.artifact.versions.length - 1;
            }
          }
        }
      });
    },

    updateCurrentArtifact: (artifact: Partial<Artifact>) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (tab) {
          tab.artifact = { ...tab.artifact, ...artifact };
        }
      });
    },

    autoSwitchToPreview: () => {
      const tab = getActiveTab(get());
      if (tab && !tab.isGenerating && tab.displayMode === ArtifactDisplayMode.Code) {
        set((state) => {
          const tab = getActiveTab(state);
          if (tab) {
            tab.displayMode = ArtifactDisplayMode.Preview;
          }
        });
      }
    },

    setPanelWidth: (width: number) => {
      set((state) => {
        state.panelWidth = Math.max(PORTAL_MIN_WIDTH, Math.min(PORTAL_MAX_WIDTH, width));
      });
    },

    getCachedContent: (artifactId: string) => {
      const cache = get().contentCache;
      const entry = cache[artifactId];
      if (!entry) return null;

      // 检查是否过期
      if (Date.now() - entry.timestamp > ARTIFACT_CACHE_TTL) {
        return null;
      }
      return entry.content;
    },

    setCachedContent: (artifactId: string, content: string) => {
      set((state) => {
        // 如果缓存满了，删除最旧的条目
        const keys = Object.keys(state.contentCache);
        if (keys.length >= ARTIFACT_CACHE_MAX_SIZE) {
          let oldestKey = keys[0];
          let oldestTime = state.contentCache[oldestKey]?.timestamp ?? Infinity;
          for (const key of keys) {
            const entry = state.contentCache[key];
            if (entry && entry.timestamp < oldestTime) {
              oldestTime = entry.timestamp;
              oldestKey = key;
            }
          }
          delete state.contentCache[oldestKey];
        }
        state.contentCache[artifactId] = {
          content,
          timestamp: Date.now(),
        };
      });
    },

    cleanupCache: () => {
      set((state) => {
        const now = Date.now();
        const keys = Object.keys(state.contentCache);
        for (const key of keys) {
          const entry = state.contentCache[key];
          if (entry && now - entry.timestamp > ARTIFACT_CACHE_TTL) {
            delete state.contentCache[key];
          }
        }
      });
    },

    addTab: (artifact: Artifact, options?: OpenArtifactTabOptions) => {
      const cached = get().getCachedContent(artifact.id);
      const now = Date.now();

      set((state) => {
        // 检查是否已存在
        const existingIndex = state.openTabs.findIndex((tab) => tab.artifact.id === artifact.id);

        if (existingIndex >= 0) {
          // 已存在，切换到该标签页并更新访问时间
          state.activeTabIndex = existingIndex;
          state.openTabs[existingIndex].lastAccessedAt = now;
          if (options?.lineRange) {
            state.openTabs[existingIndex].lineRange = options.lineRange;
          }
          if (options?.diffPreviewTruncated !== undefined) {
            state.openTabs[existingIndex].diffPreviewTruncated = options.diffPreviewTruncated;
          }
        } else {
          // 检查是否超过最大数量
          if (state.openTabs.length >= MAX_OPEN_TABS) {
            // 找到最早打开的非活动标签页并关闭
            const inactiveTabs = state.openTabs
              .map((tab, idx) => ({ tab, idx }))
              .filter(({ idx }) => idx !== state.activeTabIndex)
              .sort((a, b) => a.tab.openedAt - b.tab.openedAt);

            if (inactiveTabs.length > 0) {
              const oldestIndex = inactiveTabs[0].idx;
              state.openTabs.splice(oldestIndex, 1);
              // 调整活动标签页索引
              if (oldestIndex < state.activeTabIndex) {
                state.activeTabIndex--;
              }
            } else {
              // 所有标签页都是活动的，关闭最早的
              state.openTabs.shift();
              state.activeTabIndex = Math.max(0, state.activeTabIndex - 1);
            }
          }

          // 新增标签页
          const newTab: OpenArtifactTab = {
            artifact,
            content: cached || '',
            contentLoading: !cached,
            error: null,
            isGenerating: false,
            displayMode: ArtifactDisplayMode.Preview,
            viewingVersionIndex: -1,
            openedAt: now,
            lastAccessedAt: now,
            lineRange: options?.lineRange,
            diffPreviewTruncated: options?.diffPreviewTruncated ?? false,
          };
          state.openTabs.push(newTab);
          state.activeTabIndex = state.openTabs.length - 1;
        }
        state.isOpen = true;
      });
    },

    closeTab: (index: number) => {
      set((state) => {
        if (index < 0 || index >= state.openTabs.length) return;

        state.openTabs.splice(index, 1);

        if (state.openTabs.length === 0) {
          // 没有标签页了，关闭 Portal
          state.isOpen = false;
          state.activeTabIndex = -1;
        } else {
          // 调整活动标签页索引
          if (state.activeTabIndex >= state.openTabs.length) {
            state.activeTabIndex = state.openTabs.length - 1;
          } else if (state.activeTabIndex > index) {
            state.activeTabIndex--;
          }
        }
      });
    },

    switchTab: (index: number) => {
      set((state) => {
        if (index < 0 || index >= state.openTabs.length) return;
        state.activeTabIndex = index;
        // 更新访问时间
        state.openTabs[index].lastAccessedAt = Date.now();
      });
    },

    closeOtherTabs: (index: number) => {
      set((state) => {
        if (index < 0 || index >= state.openTabs.length) return;

        const keepTab = state.openTabs[index];
        state.openTabs = [keepTab];
        state.activeTabIndex = 0;
      });
    },

    closeAllTabs: () => {
      set((state) => {
        state.openTabs = [];
        state.activeTabIndex = -1;
        state.isOpen = false;
      });
    },

    updateTabContent: (artifactId: string, content: string, options?: { truncated?: boolean }) => {
      const state = get();
      state.setCachedContent(artifactId, content);
      set((state) => {
        const tab = state.openTabs.find((t) => t.artifact.id === artifactId);
        if (tab) {
          tab.content = content;
          if (options?.truncated) {
            tab.diffPreviewTruncated = true;
          }
        }
      });
    },

    updateTabLoading: (artifactId: string, loading: boolean) => {
      set((state) => {
        const tab = state.openTabs.find((t) => t.artifact.id === artifactId);
        if (tab) {
          tab.contentLoading = loading;
        }
      });
    },

    updateTabError: (artifactId: string, error: ArtifactError | null) => {
      set((state) => {
        const tab = state.openTabs.find((t) => t.artifact.id === artifactId);
        if (tab) {
          tab.error = error;
        }
      });
    },

    // ==================== 版本历史 Actions ====================
    createVersion: (description?: string) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (!tab || !tab.content) return;

        // 初始化版本数组
        if (!tab.artifact.versions) {
          tab.artifact.versions = [];
        }

        // 创建新版本
        const newVersion = {
          versionId: `v${Date.now()}`,
          versionNumber: tab.artifact.versions.length + 1,
          content: tab.content,
          createdAt: new Date().toISOString(),
          description,
        };

        tab.artifact.versions.push(newVersion);

        // 限制版本数量，删除最旧的版本
        while (tab.artifact.versions.length > MAX_VERSIONS_PER_ARTIFACT) {
          tab.artifact.versions.shift();
        }

        tab.artifact.currentVersionIndex = tab.artifact.versions.length - 1;
        tab.viewingVersionIndex = -1; // 重置为查看最新

        // 更新缓存
        state.contentCache[tab.artifact.id] = {
          content: tab.content,
          timestamp: Date.now(),
        };
      });
    },

    switchToVersion: (versionIndex: number, content?: string) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (!tab) return;

        tab.viewingVersionIndex = versionIndex;

        if (versionIndex === -1) {
          // 查看最新内容（从缓存恢复）
          const cached = state.contentCache[tab.artifact.id];
          if (cached) {
            tab.content = cached.content;
          }
        } else if (content !== undefined) {
          // 如果提供了内容，直接使用提供的内容
          tab.content = content;
        } else if (tab.artifact.versions && tab.artifact.versions[versionIndex]) {
          // 查看历史版本
          tab.content = tab.artifact.versions[versionIndex].content;
        }
      });
    },

    rollbackToVersion: (versionIndex: number, content?: string) => {
      set((state) => {
        const tab = getActiveTab(state);
        if (!tab) return;

        let targetContent = content;

        if (content === undefined && tab.artifact.versions && tab.artifact.versions[versionIndex]) {
          targetContent = tab.artifact.versions[versionIndex].content;
          // 删除该版本之后的所有版本
          tab.artifact.versions = tab.artifact.versions.slice(0, versionIndex + 1);
          tab.artifact.currentVersionIndex = versionIndex;
        }

        if (targetContent !== undefined) {
          tab.content = targetContent;
          tab.viewingVersionIndex = -1;

          // 更新缓存
          state.contentCache[tab.artifact.id] = {
            content: targetContent,
            timestamp: Date.now(),
          };
        }
      });
    },

    getVersions: () => {
      const state = get();
      const tab = getActiveTab(state);
      return tab?.artifact.versions;
    },

    getViewingVersionIndex: () => {
      const state = get();
      const tab = getActiveTab(state);
      return tab?.viewingVersionIndex ?? -1;
    },

    // ==================== 协同编辑 Actions ====================
    markAsDirty: (artifactId: string, content: string) => {
      set((state) => {
        state.dirtyArtifacts[artifactId] = content;
      });
    },

    clearDirtyState: (artifactId: string) => {
      set((state) => {
        delete state.dirtyArtifacts[artifactId];
      });
    },

    getDirtyArtifacts: () => {
      return get().dirtyArtifacts;
    },
  })),
);

// ==================== Selector Hooks ====================
// 使用这些 hooks 可以减少不必要的重渲染，只在相关状态变化时触发更新

/** 选择器：获取当前激活的 tab */
export const useActiveTab = () =>
  useArtifactPortalStore((state) => {
    if (state.activeTabIndex >= 0 && state.activeTabIndex < state.openTabs.length) {
      return state.openTabs[state.activeTabIndex];
    }
    return null;
  });

/** 选择器：Portal 是否打开 */
export const useIsPortalOpen = () => useArtifactPortalStore((state) => state.isOpen);

/** 选择器：当前 artifact */
export const useCurrentArtifact = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.artifact ?? null;
  });

/** 选择器：当前内容 */
export const useArtifactContent = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.content ?? '';
  });

/** 选择器：当前加载状态 */
export const useArtifactLoading = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.contentLoading ?? false;
  });

/** 选择器：当前错误 */
export const useArtifactError = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.error ?? null;
  });

/** 选择器：是否正在生成 */
export const useIsGenerating = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.isGenerating ?? false;
  });

/** 选择器：当前显示模式 */
export const useDisplayMode = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.displayMode ?? ArtifactDisplayMode.Preview;
  });

/** 选择器：面板宽度 */
export const usePanelWidth = () => useArtifactPortalStore((state) => state.panelWidth);

/** 选择器：打开的标签页信息 */
export const useOpenTabs = () =>
  useArtifactPortalStore(
    useShallow((state) => ({
      tabs: state.openTabs,
      activeIndex: state.activeTabIndex,
    })),
  );

/** 选择器：标签页数量 */
export const useTabCount = () => useArtifactPortalStore((state) => state.openTabs.length);

/** 选择器：当前 artifact 的版本列表 */
export const useArtifactVersions = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.artifact.versions ?? EMPTY_VERSIONS;
  });

/** 选择器：当前查看的版本索引（-1 表示最新） */
export const useViewingVersionIndex = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return tab?.viewingVersionIndex ?? -1;
  });

/** 选择器：是否正在查看历史版本 */
export const useIsViewingHistory = () =>
  useArtifactPortalStore((state) => {
    const tab = getActiveTab(state);
    return (tab?.viewingVersionIndex ?? -1) >= 0;
  });

export default useArtifactPortalStore;
