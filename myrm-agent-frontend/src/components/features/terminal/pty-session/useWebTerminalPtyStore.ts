/**
 * Web Terminal PTY Zustand Store
 * Web 端持久化 PTY 会话流状态机与脱钩挂载调度器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { create } from 'zustand';
import {
  appendRawChunkToLines,
} from './webTerminalAnsiEmulator';
import {
  PtySessionDescriptor,
  TerminalBufferLine,
} from './webTerminalTypes';

interface WebTerminalPtyStoreState {
  sessions: PtySessionDescriptor[];
  activeSessionId: string | null;
  buffers: Record<string, TerminalBufferLine[]>;
  isFullscreen: boolean;
  inputBuffer: string;

  // Actions
  createSession: (title?: string, cwd?: string) => string;
  closeSession: (id: string) => void;
  detachSession: (id: string) => void;
  attachSession: (id: string) => void;
  setActiveSessionId: (id: string | null) => void;
  writeInput: (id: string, input: string) => void;
  receiveOutput: (id: string, rawChunk: string) => void;
  clearBuffer: (id: string) => void;
  setIsFullscreen: (fullscreen: boolean) => void;
  setInputBuffer: (text: string) => void;
  resetToDefault: () => void;
}

const INITIAL_SESSIONS: PtySessionDescriptor[] = [
  {
    id: 'pty-session-main',
    title: '终端 1 (zsh)',
    pid: 14208,
    cwd: '/workspace/open-perplexity',
    shell: '/bin/zsh',
    cols: 80,
    rows: 24,
    status: 'connected',
    createdAt: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    lastActiveAt: new Date().toISOString(),
    isDetached: false,
  },
  {
    id: 'pty-session-daemon',
    title: '构建守护 (Vite Dev)',
    pid: 14220,
    cwd: '/workspace/open-perplexity/myrm-agent-frontend',
    shell: '/bin/bash',
    cols: 80,
    rows: 24,
    status: 'detached',
    createdAt: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    isDetached: true,
  },
];

const INITIAL_BUFFERS: Record<string, TerminalBufferLine[]> = {
  'pty-session-main': appendRawChunkToLines(
    [],
    '\x1b[32m✔ Myrm Web PTY Attached\x1b[0m\n\x1b[34m➜\x1b[0m \x1b[36mopen-perplexity\x1b[0m \x1b[33mgit:(main)\x1b[0m ready for interactive commands\n$ '
  ),
  'pty-session-daemon': appendRawChunkToLines(
    [],
    '[Vite] VITE v5.4.2 ready in 240 ms\n➜  Local:   http://localhost:5173/\n\x1b[33m[PTY Detached: Running persistently in background daemon]\x1b[0m\n'
  ),
};

export const useWebTerminalPtyStore = create<WebTerminalPtyStoreState>((set, get) => ({
  sessions: INITIAL_SESSIONS,
  activeSessionId: 'pty-session-main',
  buffers: INITIAL_BUFFERS,
  isFullscreen: false,
  inputBuffer: '',

  createSession: (title?: string, cwd?: string) => {
    const id = `pty-${Date.now().toString(36)}`;
    const sessionCount = get().sessions.length + 1;
    const newSession: PtySessionDescriptor = {
      id,
      title: title || `终端 ${sessionCount} (bash)`,
      pid: Math.floor(10000 + Math.random() * 89999),
      cwd: cwd || '/workspace/open-perplexity',
      shell: '/bin/bash',
      cols: 80,
      rows: 24,
      status: 'connected',
      createdAt: new Date().toISOString(),
      lastActiveAt: new Date().toISOString(),
      isDetached: false,
    };

    const initialLines = appendRawChunkToLines(
      [],
      `\x1b[32m[PTY Session Created: PID ${newSession.pid}]\x1b[0m\n$ `
    );

    set((state) => ({
      sessions: [...state.sessions, newSession],
      activeSessionId: id,
      buffers: {
        ...state.buffers,
        [id]: initialLines,
      },
    }));

    return id;
  },

  closeSession: (id: string) => {
    set((state) => {
      const remaining = state.sessions.filter((s) => s.id !== id);
      const nextActiveId =
        state.activeSessionId === id
          ? remaining.length > 0
            ? remaining[0].id
            : null
          : state.activeSessionId;

      return {
        sessions: remaining,
        activeSessionId: nextActiveId,
      };
    });
  },

  detachSession: (id: string) => {
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id === id) {
          return {
            ...s,
            isDetached: true,
            status: 'detached',
            lastActiveAt: new Date().toISOString(),
          };
        }
        return s;
      }),
    }));

    get().receiveOutput(
      id,
      '\n\x1b[33m[PTY Session Detached: Process kept running persistently in background]\x1b[0m\n'
    );
  },

  attachSession: (id: string) => {
    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id === id) {
          return {
            ...s,
            isDetached: false,
            status: 'connected',
            lastActiveAt: new Date().toISOString(),
          };
        }
        return s;
      }),
      activeSessionId: id,
    }));

    get().receiveOutput(
      id,
      '\x1b[32m[PTY Session Re-attached successfully]\x1b[0m\n$ '
    );
  },

  setActiveSessionId: (id: string | null) => {
    set({ activeSessionId: id });
  },

  writeInput: (id: string, input: string) => {
    const session = get().sessions.find((s) => s.id === id);
    if (!session || session.status === 'terminated') {
      return;
    }

    if (input === '\r') {
      const currentInput = get().inputBuffer;
      get().receiveOutput(id, `\n\x1b[90m[exec: ${currentInput}]\x1b[0m\n$ `);
      set({ inputBuffer: '' });
      return;
    }

    if (input === '\x03') {
      get().receiveOutput(id, '^C\n$ ');
      set({ inputBuffer: '' });
      return;
    }

    if (input === '\b') {
      set((state) => ({
        inputBuffer: state.inputBuffer.slice(0, -1),
      }));
      return;
    }

    // 常用字符追加输入缓冲
    set((state) => ({
      inputBuffer: state.inputBuffer + input,
    }));
  },

  receiveOutput: (id: string, rawChunk: string) => {
    set((state) => {
      const existing = state.buffers[id] || [];
      const updated = appendRawChunkToLines(existing, rawChunk);
      return {
        buffers: {
          ...state.buffers,
          [id]: updated,
        },
      };
    });
  },

  clearBuffer: (id: string) => {
    set((state) => ({
      buffers: {
        ...state.buffers,
        [id]: [],
      },
      inputBuffer: '',
    }));
  },

  setIsFullscreen: (fullscreen: boolean) => {
    set({ isFullscreen: fullscreen });
  },

  setInputBuffer: (text: string) => {
    set({ inputBuffer: text });
  },

  resetToDefault: () => {
    set({
      sessions: JSON.parse(JSON.stringify(INITIAL_SESSIONS)) as PtySessionDescriptor[],
      activeSessionId: 'pty-session-main',
      buffers: JSON.parse(JSON.stringify(INITIAL_BUFFERS)) as Record<string, TerminalBufferLine[]>,
      isFullscreen: false,
      inputBuffer: '',
    });
  },
}));
