/**
 * [INPUT]
 * - @/lib/utils/imeUtils::isImeComposing (POS: IME 输入法兼容性守卫工具函数)
 *
 * [OUTPUT]
 * - resolveDualChannelAction: 聊天输入框双通道键盘事件路由判定（实时引导 vs 非中断排队）
 *
 * [POS]
 * 聊天输入框双通道键盘交互路由核心。负责在运行时与空闲态下对 Enter、Alt+Enter、Shift+Enter 及输入法合成态进行纯函数分流决策。
 */
import { isImeComposing, type KeyboardEventLike } from '@/lib/utils/imeUtils';

export type DualChannelAction = 'none' | 'submit' | 'queue';

export interface DualChannelKeyEvent extends KeyboardEventLike {
  key: string;
  altKey: boolean;
  shiftKey: boolean;
  preventDefault?: () => void;
}

/**
 * 判定聊天输入框的键盘回车分流动作
 *
 * 核心规范与操作心智：
 * 1. 运行时 (loading=true)：
 *    - Enter (无修饰键)：触发实时引导纠偏 (Steering / Redirect)；
 *    - ⌥+Enter (Alt+Enter)：触发非中断排队跟进 (Follow-up Queue)；
 *    - Shift+Enter：保持多行文本换行，不拦截；
 * 2. 空闲时 (loading=false)：
 *    - Enter 或 Alt+Enter：触发常规消息提交发送；
 *    - Shift+Enter：保持多行文本换行，不拦截；
 * 3. 输入法合成态 (IME isComposing)：
 *    - 严格放行，避免拼音/候选词确认击发误触。
 */
export function resolveDualChannelAction(
  e: DualChannelKeyEvent,
  options: { loading: boolean },
): DualChannelAction {
  if (isImeComposing(e)) {
    return 'none';
  }

  if (e.key !== 'Enter') {
    return 'none';
  }

  if (e.altKey) {
    e.preventDefault?.();
    return options.loading ? 'queue' : 'submit';
  }

  if (!e.shiftKey) {
    e.preventDefault?.();
    return 'submit';
  }

  return 'none';
}
