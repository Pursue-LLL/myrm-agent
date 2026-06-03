/**
 * 认证状态管理 Store
 *
 * 管理用户认证状态：
 * - 本地模式（Tauri/Local）：从后端获取真实 admin 用户信息，自动认证
 * - Sandbox 模式：必须 OAuth 登录
 *
 * Logout 会同时调用后端 /auth/logout 清除 httpOnly Cookie（WebUI Remote 模式需要）。
 */

import { create } from 'zustand';

import {
  isGuest as checkIsGuest,
  isAuthenticated as checkIsAuthenticated,
  setAuthToken,
  clearAuthToken,
} from '@/lib/guest';
import { parseCpAuthTokenUserId } from '@/lib/auth-cp-token';
import { getWebuiUrl } from '@/lib/api';

interface User {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  role?: string;
}

interface AuthState {
  // 状态
  isGuest: boolean;
  isAuthenticated: boolean;
  isInitialized: boolean;
  isLoading: boolean;
  user: User | null;
  token: string | null;

  // 动作
  initAuth: () => void;
  initTauriLocalUser: () => Promise<void>;
  login: (token: string, user?: User) => Promise<void>;
  loginMock: () => void;
  logout: () => Promise<void>;
}

const useAuthStore = create<AuthState>((set, get) => ({
  // 初始状态
  isGuest: true,
  isAuthenticated: false,
  isInitialized: false,
  isLoading: false,
  user: null,
  token: null,

  /**
   * 初始化认证状态（Sandbox 模式）
   * 在应用启动时调用，从 localStorage 读取状态
   */
  initAuth: () => {
    if (get().isInitialized) return;

    const isGuest = checkIsGuest();
    const isAuthenticated = checkIsAuthenticated();

    // 尝试从 localStorage 恢复用户信息
    let user: User | null = null;
    let token: string | null = null;
    if (typeof window !== 'undefined') {
      const savedUser = localStorage.getItem('auth_user');
      if (savedUser) {
        try {
          user = JSON.parse(savedUser);
        } catch {
          // ignore
        }
      }
      token = localStorage.getItem('auth_token');
      if (token?.startsWith('mock-token-')) {
        token = null; // mock token 不算真实 token
      }
    }

    set({
      isGuest,
      isAuthenticated,
      user,
      token,
      isInitialized: true,
    });
  },

  /**
   * 初始化本地用户（Tauri/Local 模式）
   *
   * 从后端 /webui/auth/status 获取真实用户信息（ID、用户名、角色）。
   * 后端不可达时回退到静态 fallback。
   */
  initTauriLocalUser: async () => {
    if (get().isInitialized) return;
    set({ isInitialized: true });

    let localUser: User = {
      id: 'local-user',
      email: 'local@tauri.app',
      display_name: 'Local User',
      role: 'admin',
    };

    try {
      const res = await fetch(getWebuiUrl('/auth/status'), {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        if (data.user_id) {
          localUser = {
            id: data.user_id,
            email: 'local@tauri.app',
            display_name: data.username || 'Local User',
            role: data.role || 'admin',
          };
        }
      }
    } catch {
      // best-effort: 后端不可达时使用 fallback
    }

    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', 'local_user_token');
      localStorage.setItem('auth_user', JSON.stringify(localUser));
    }

    set({
      isGuest: false,
      isAuthenticated: true,
      user: localUser,
      token: 'local_user_token',
      isInitialized: true,
    });
  },

  /**
   * 用户登录（Sandbox 模式）
   * @param token - 认证 Token
   * @param user - 用户信息（可选，如果不提供则从后端获取）
   */
  login: async (token: string, user?: User) => {
    set({ isLoading: true });

    try {
      setAuthToken(token);

      let resolvedUser = user;
      if (!resolvedUser) {
        const userId = parseCpAuthTokenUserId(token);
        resolvedUser = {
          id: userId ?? 'authenticated',
          email: '',
        };
      }

      // 保存用户信息到 localStorage
      if (typeof window !== 'undefined' && resolvedUser) {
        localStorage.setItem('auth_user', JSON.stringify(resolvedUser));
      }

      set({
        isGuest: false,
        isAuthenticated: true,
        user: resolvedUser || null,
        token,
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  /**
   * 开发模式 mock 登录
   *
   * 生成与 OAuth 登录格式一致的测试 token，以便完整测试配置同步流程。
   */
  loginMock: () => {
    const testToken = `test-user-token-${Date.now()}`;
    const mockUser: User = {
      id: 'local-user',
      email: 'test@example.com',
      display_name: 'Test User',
    };

    setAuthToken(testToken);

    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_user', JSON.stringify(mockUser));
    }

    set({
      isGuest: false,
      isAuthenticated: true,
      user: mockUser,
      token: testToken,
    });
  },

  /**
   * 用户登出
   *
   * 同时调用后端 /auth/logout 清除 httpOnly Cookie（WebUI Remote 模式需要）。
   */
  logout: async () => {
    try {
      await fetch(getWebuiUrl('/auth/logout'), {
        method: 'POST',
        credentials: 'include',
      });
    } catch {
      // best-effort: 后端不可达时仍清理前端状态
    }

    clearAuthToken();

    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_user');
    }

    set({
      isGuest: true,
      isAuthenticated: false,
      user: null,
      token: null,
    });
  },
}));

export default useAuthStore;
