/**
 * [INPUT]
 * - 审批请求的工具名与参数
 *
 * [OUTPUT]
 * - BrowserSessionAction: 浏览器会话审批卡覆盖的四个动作
 * - resolveBrowserSession: 判断一条审批是否是浏览器会话操作，返回动作与站点
 *
 * [POS]
 * 浏览器「登录状态」审批的识别规则；动作的标题与说明在 locales 里，不在这里。
 */

export const BROWSER_SESSION_ACTIONS = ['save_session', 'restore_session', 'list_sessions', 'delete_session'] as const;

export type BrowserSessionAction = (typeof BROWSER_SESSION_ACTIONS)[number];

export interface BrowserSessionApproval {
  action: BrowserSessionAction;
  /** 空串表示不限站点（例如列出全部已保存的登录状态）。 */
  domain: string;
}

function isBrowserSessionAction(value: unknown): value is BrowserSessionAction {
  return typeof value === 'string' && (BROWSER_SESSION_ACTIONS as readonly string[]).includes(value);
}

export function resolveBrowserSession(
  toolName: string,
  toolInput: Record<string, unknown>,
): BrowserSessionApproval | null {
  if (toolName !== 'browser_manage' || !isBrowserSessionAction(toolInput.action)) {
    return null;
  }
  return { action: toolInput.action, domain: String(toolInput.value ?? '') };
}
