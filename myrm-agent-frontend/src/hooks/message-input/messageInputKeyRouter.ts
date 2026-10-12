/**
 * [INPUT]
 * - @/lib/utils/imeUtils::isImeComposing (POS: IME 输入法兼容性守卫工具函数)
 *
 * [OUTPUT]
 * - resolveDualChannelAction: 聊天输入框双通道键盘事件路由判定（提交 vs 非中断排队）
 * - resolveBusySubmitMode: 运行中一次普通提交的落点（redirect / steer / queue），带附件一律排队
 * - resolveBusyPlaceholderKey: 运行中输入框占位提示的文案键，与提交落点一一对应
 *
 * [POS]
 * 聊天输入框双通道键盘交互路由核心。负责在运行时与空闲态、紧凑与全屏编辑模式下，
 * 对 Enter、Alt+Enter、Ctrl/⌘+Enter、Shift+Enter 及输入法合成态进行纯函数分流决策，
 * 并给出运行中普通提交的实际落点及其占位提示，让提示与行为同源。
 */
import { isImeComposing, type KeyboardEventLike } from '@/lib/utils/imeUtils';
import type { BusyInputMode } from '@/store/chat/types';

export type DualChannelAction = 'none' | 'submit' | 'queue';

export interface DualChannelKeyEvent extends KeyboardEventLike {
  key: string;
  altKey: boolean;
  shiftKey: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  preventDefault?: () => void;
}

export interface DualChannelOptions {
  /** The agent is running a turn. */
  loading: boolean;
  /** Full-screen editor: writing long text, so a bare Enter must not send. */
  expanded?: boolean;
}

/**
 * 判定聊天输入框的键盘回车分流动作
 *
 * 核心规范与操作心智：
 * 1. 运行时 (loading=true)：
 *    - Enter (无修饰键)：提交，落点由 resolveBusySubmitMode 决定（默认立即纠偏，可配置为引导或排队）；
 *    - ⌥+Enter (Alt+Enter)：始终非中断排队跟进 (Follow-up Queue)；
 *    - Shift+Enter：保持多行文本换行，不拦截；
 * 2. 空闲时 (loading=false)：
 *    - Enter 或 Alt+Enter：触发常规消息提交发送；
 *    - Shift+Enter：保持多行文本换行，不拦截；
 * 3. 全屏编辑 (expanded=true)：
 *    - Enter (无修饰键)：保持换行，不拦截；
 *    - Ctrl/⌘+Enter：提交（运行时落点同 Enter）；Alt+Enter 的排队语义不变；
 * 4. 输入法合成态 (IME isComposing)：
 *    - 严格放行，避免拼音/候选词确认击发误触。
 */
export function resolveDualChannelAction(e: DualChannelKeyEvent, options: DualChannelOptions): DualChannelAction {
  if (isImeComposing(e)) {
    return 'none';
  }

  if (e.key !== 'Enter') {
    return 'none';
  }

  // 只要按下 Shift（例如 Shift+Enter 或 Shift+Alt+Enter），一律保持原生多行换行，绝不误触提前提交或排队
  if (e.shiftKey) {
    return 'none';
  }

  if (e.altKey) {
    e.preventDefault?.();
    return options.loading ? 'queue' : 'submit';
  }

  if (options.expanded && !e.ctrlKey && !e.metaKey) {
    return 'none';
  }

  e.preventDefault?.();
  return 'submit';
}

/**
 * 运行中一次普通提交（Enter）的落点。redirect 与 steer 只携带文本，
 * 因此带附件的消息一律改走队列，避免附件被丢弃。
 */
export function resolveBusySubmitMode(hasFiles: boolean, busyInputMode: BusyInputMode | undefined): BusyInputMode {
  return hasFiles ? 'queue' : (busyInputMode ?? 'redirect');
}

/** 运行中输入框占位提示的文案键（chat 命名空间）；紧凑输入框与全屏编辑器的发送快捷键不同，各有一套文案。 */
export function resolveBusyPlaceholderKey(mode: BusyInputMode, expanded: boolean): string {
  return expanded ? `queue.busyPlaceholderExpanded.${mode}` : `queue.busyPlaceholder.${mode}`;
}
