import { writeText as tauriWriteText, readText as tauriReadText } from '@tauri-apps/plugin-clipboard-manager';
import { ask } from '@tauri-apps/plugin-dialog';
import { toast } from 'sonner';

/**
 * 检测当前是否运行在 Tauri 环境中
 */
export const isTauri = (): boolean => {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

const CLIPBOARD_PERMISSION_KEY = 'myrm_clipboard_read_permission';

/**
 * 安全地将文本写入剪贴板
 * 在 Tauri 环境下使用原生插件，Web 环境下使用 navigator.clipboard
 * 写入成功后会自动触发 Toast 提示
 *
 * @param text 要写入剪贴板的文本
 * @param silent 是否静默写入（不显示 Toast 提示），默认 false
 */
export const writeToClipboard = async (text: string, silent = false): Promise<boolean> => {
  try {
    if (isTauri()) {
      await tauriWriteText(text);
    } else {
      await navigator.clipboard.writeText(text);
    }

    if (!silent) {
      toast.success('已复制到剪贴板');
    }
    return true;
  } catch (error) {
    console.error('Failed to write to clipboard:', error);
    if (!silent) {
      toast.error('复制失败，请检查剪贴板权限');
    }
    return false;
  }
};

/**
 * 智能体发起的剪贴板写入操作，必须经过用户确认
 *
 * @param text 要写入剪贴板的文本
 */
export const writeToClipboardByAgent = async (text: string): Promise<boolean> => {
  if (typeof window === 'undefined') return false;

  let allowed = false;
  if (isTauri()) {
    try {
      allowed = await ask(
        `智能体请求将以下内容写入您的剪贴板：\n\n${text.substring(0, 100)}${text.length > 100 ? '...' : ''}\n\n是否允许？`,
        {
          title: '安全警告：剪贴板写入请求',
          kind: 'warning',
          okLabel: '允许写入',
          cancelLabel: '拒绝',
        },
      );
    } catch (e) {
      console.error('Dialog error:', e);
      allowed = false;
    }
  } else {
    allowed = window.confirm(
      `智能体请求将以下内容写入您的剪贴板：\n\n${text.substring(0, 100)}${text.length > 100 ? '...' : ''}\n\n是否允许？`,
    );
  }

  if (allowed) {
    const success = await writeToClipboard(text, true);
    if (success) {
      toast.success('智能体已将内容写入剪贴板');
    }
    return success;
  } else {
    toast.error('已拒绝智能体写入剪贴板');
    return false;
  }
};

/**
 * 请求读取剪贴板的权限
 */
const requestReadPermission = async (): Promise<boolean> => {
  if (typeof window === 'undefined') return false;

  // 检查是否已经授权
  const savedPermission = localStorage.getItem(CLIPBOARD_PERMISSION_KEY);
  if (savedPermission === 'granted') {
    return true;
  }
  if (savedPermission === 'denied') {
    toast.error('读取剪贴板已被拒绝，请在设置中更改');
    return false;
  }

  // 如果在 Tauri 环境，使用原生对话框
  if (isTauri()) {
    try {
      const allowed = await ask('应用请求读取您的剪贴板内容，是否允许？\n\n允许后将不再提示。', {
        title: '剪贴板权限请求',
        kind: 'info',
        okLabel: '允许',
        cancelLabel: '拒绝',
      });

      if (allowed) {
        localStorage.setItem(CLIPBOARD_PERMISSION_KEY, 'granted');
        return true;
      } else {
        // 不持久化拒绝，以便下次还能问，或者持久化？
        // 为了体验，暂时不持久化拒绝，或者只在本次会话拒绝
        toast.error('已拒绝读取剪贴板');
        return false;
      }
    } catch (e) {
      console.error('Dialog error:', e);
      return false;
    }
  } else {
    // Web 环境下，通常浏览器会自己弹窗，但我们可以先用 confirm 确认
    const allowed = window.confirm('应用请求读取您的剪贴板内容，是否允许？');
    if (allowed) {
      localStorage.setItem(CLIPBOARD_PERMISSION_KEY, 'granted');
      return true;
    } else {
      toast.error('已拒绝读取剪贴板');
      return false;
    }
  }
};

/**
 * 安全地从剪贴板读取文本
 * 在 Tauri 环境下使用原生插件，Web 环境下使用 navigator.clipboard
 * 包含显式的权限管控
 *
 * @returns 剪贴板中的文本内容
 */
export const readFromClipboard = async (): Promise<string> => {
  try {
    const hasPermission = await requestReadPermission();
    if (!hasPermission) {
      throw new Error('Permission denied');
    }

    if (isTauri()) {
      return await tauriReadText();
    } else {
      return await navigator.clipboard.readText();
    }
  } catch (error) {
    console.error('Failed to read from clipboard:', error);
    toast.error('读取剪贴板失败，请检查权限');
    throw error;
  }
};
