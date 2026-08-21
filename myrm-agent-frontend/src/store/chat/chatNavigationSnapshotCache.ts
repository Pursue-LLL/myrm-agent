/**
 * [INPUT]
 * @/store/chat/types::ChatState (POS: useChatStore 状态与操作方法契约)
 *
 * [OUTPUT]
 * extractNavigationSnapshot / getChatNavigationSnapshot / saveChatNavigationSnapshot / clearChatNavigationSnapshot:
 * L1 (In-Memory Map) + L2 (SessionStorage Persist) 双级快照缓存总线，支撑 Fast UI Restore 0ms 视觉秒开恢复。
 *
 * [POS]
 * 会话瞬时恢复核心缓存层。L1 负责单页内高频切换会话，L2 负责浏览器刷新(F5/Cmd+R)、桌面端热重载下的会话视口 0ms 秒开还原与 Quota 容灾。
 */
import type { ChatState } from '@/store/chat/types';
import {
  createEmptyPaneMessageSnapshot,
  extractChatSessionConfig,
  mergeChatSessionConfig,
} from '@/store/chat/chatSessionConfig';

const MAX_L1_ENTRIES = 20;
const MAX_L2_ENTRIES = 3;
const MAX_L2_SERIALIZED_BYTES = 300 * 1024; // 300 KB 单快照容量硬上限
const L2_STORAGE_PREFIX = 'myrm_nav_snap_';
const L2_INDEX_KEY = 'myrm_nav_snap_index';

const navigationSnapshots = new Map<string, Partial<ChatState>>();

/**
 * 提取可持久化/恢复的视口快照切片
 */
export function extractNavigationSnapshot(state: ChatState): Partial<ChatState> {
  return {
    messages: state.messages,
    loading: state.loading,
    messageAppeared: state.messageAppeared,
    isMessagesLoaded: state.isMessagesLoaded,
    compactedSummary: state.compactedSummary,
    compactedBeforeId: state.compactedBeforeId,
    contextBranches: state.contextBranches,
    contextPinnedFiles: state.contextPinnedFiles,
    contextBranchesLoadError: state.contextBranchesLoadError,
    contextPinnedFilesLoadError: state.contextPinnedFilesLoadError,
    workspaceDir: state.workspaceDir,
    incognitoMode: state.incognitoMode,
    sandboxMode: state.sandboxMode,
    notFound: state.notFound,
    loadError: state.loadError,
    hideAttachList: state.hideAttachList,
    hasUsedImagesInCurrentChat: state.hasUsedImagesInCurrentChat,
    files: state.files,
    cameraFrames: state.cameraFrames,
    mentionReferences: state.mentionReferences,
    ...extractChatSessionConfig(state),
  };
}

/**
 * L2 持久化数据安全脱敏与轻量化裁剪
 * 剔除超大 Base64/二进制与临时 DOM 引用，重置 loading 态为 false（防刷新后挂死 loading）
 */
function sanitizeSnapshotForL2Storage(snapshot: Partial<ChatState>): Partial<ChatState> {
  const cloned = structuredClone(snapshot);
  cloned.loading = false;
  cloned.cameraFrames = undefined;

  // 如果包含消息列表，裁剪可能挂载的大尺寸 data:image base64 url
  if (Array.isArray(cloned.messages)) {
    cloned.messages = cloned.messages.map((msg) => {
      if (!msg.files || msg.files.length === 0) {
        return msg;
      }
      const safeFiles = msg.files.map((file) => {
        if (typeof file.url === 'string' && file.url.startsWith('data:image/') && file.url.length > 1024) {
          return { ...file, url: '' };
        }
        return file;
      });
      return { ...msg, files: safeFiles };
    });
  }

  return cloned;
}

function getL2Index(): string[] {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return [];
  }
  try {
    const raw = window.sessionStorage.getItem(L2_INDEX_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function saveL2Index(index: string[]): void {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return;
  }
  try {
    window.sessionStorage.setItem(L2_INDEX_KEY, JSON.stringify(index));
  } catch {
    // 忽略异常，降级处理
  }
}

function saveL2Snapshot(chatId: string, snapshot: Partial<ChatState>): void {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return;
  }
  // 隐身模式不写入持久化存储
  if (snapshot.incognitoMode) {
    return;
  }

  try {
    const sanitized = sanitizeSnapshotForL2Storage(snapshot);
    const serialized = JSON.stringify(sanitized);

    // 容量上限拦截
    if (serialized.length > MAX_L2_SERIALIZED_BYTES) {
      return;
    }

    const key = `${L2_STORAGE_PREFIX}${chatId}`;
    window.sessionStorage.setItem(key, serialized);

    let index = getL2Index().filter((id) => id !== chatId);
    index.unshift(chatId);

    // LRU 淘汰旧条目
    while (index.length > MAX_L2_ENTRIES) {
      const evictedId = index.pop();
      if (evictedId) {
        window.sessionStorage.removeItem(`${L2_STORAGE_PREFIX}${evictedId}`);
      }
    }

    saveL2Index(index);
  } catch {
    // 遇到 QuotaExceededError 或隐私模式限制时自动静默忽略，不破坏主线程
  }
}

function readL2Snapshot(chatId: string): Partial<ChatState> | null {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return null;
  }
  try {
    const key = `${L2_STORAGE_PREFIX}${chatId}`;
    const raw = window.sessionStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as Partial<ChatState>;
  } catch {
    return null;
  }
}

function removeL2Snapshot(chatId: string): void {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return;
  }
  try {
    window.sessionStorage.removeItem(`${L2_STORAGE_PREFIX}${chatId}`);
    const index = getL2Index().filter((id) => id !== chatId);
    saveL2Index(index);
  } catch {
    // 忽略异常
  }
}

export function resolvePaneSnapshotBase(
  chatId: string,
  paneSnapshot: Partial<ChatState> | null | undefined,
): Partial<ChatState> {
  const lruSnapshot = getChatNavigationSnapshot(chatId);
  const messageBase = createEmptyPaneMessageSnapshot();
  const withLru = lruSnapshot ? mergeChatSessionConfig(messageBase, lruSnapshot) : messageBase;
  if (!paneSnapshot) {
    return withLru;
  }
  return mergeChatSessionConfig(
    {
      ...withLru,
      ...paneSnapshot,
    },
    paneSnapshot,
  );
}

/**
 * 读取快照：优先命中 L1 In-Memory，若未命中则从 L2 SessionStorage 回填并温热 L1
 */
export function getChatNavigationSnapshot(chatId: string): Partial<ChatState> | null {
  const l1Snapshot = navigationSnapshots.get(chatId);
  if (l1Snapshot) {
    return structuredClone(l1Snapshot);
  }

  // L1 未命中，回退查找 L2 持久化快照
  const l2Snapshot = readL2Snapshot(chatId);
  if (l2Snapshot) {
    // 回填温热 L1
    navigationSnapshots.set(chatId, structuredClone(l2Snapshot));
    return structuredClone(l2Snapshot);
  }

  return null;
}

/**
 * 存储快照：同步写入 L1 内存 LRU 与 L2 SessionStorage 持久化存储
 */
export function saveChatNavigationSnapshot(chatId: string, snapshot: Partial<ChatState>): void {
  if (navigationSnapshots.has(chatId)) {
    navigationSnapshots.delete(chatId);
  }
  navigationSnapshots.set(chatId, structuredClone(snapshot));

  while (navigationSnapshots.size > MAX_L1_ENTRIES) {
    const oldestKey = navigationSnapshots.keys().next().value;
    if (!oldestKey) {
      break;
    }
    navigationSnapshots.delete(oldestKey);
  }

  // 同步写入 L2 持久化存储
  saveL2Snapshot(chatId, snapshot);
}

export function clearChatNavigationSnapshot(chatId: string): void {
  navigationSnapshots.delete(chatId);
  removeL2Snapshot(chatId);
}

export function resetChatNavigationSnapshotsForTests(): void {
  navigationSnapshots.clear();
  if (typeof window !== 'undefined' && window.sessionStorage) {
    const index = getL2Index();
    for (const id of index) {
      window.sessionStorage.removeItem(`${L2_STORAGE_PREFIX}${id}`);
    }
    window.sessionStorage.removeItem(L2_INDEX_KEY);
  }
}

export function getChatNavigationSnapshotCountForTests(): number {
  return navigationSnapshots.size;
}
