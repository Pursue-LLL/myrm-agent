/**
 * [INPUT]
 * - @/lib/utils/urlUtils::isValidExternalUrl (POS: 外链协议白名单，仅 http/https)
 * - @/lib/tauri::isTauriEnvironment (POS: Tauri 原生桥接层环境探测)
 * - @/store/useExternalLinkConfirmStore (POS: 桌面端外链确认弹窗的单槽状态，含单飞与拒绝后静默)
 *
 * [OUTPUT]
 * - requestUntrustedLink: 不可信内嵌内容（widget / MCP App）请求打开外链的统一入口
 *
 * [POS]
 * 桌面壳没有浏览器的弹窗拦截，内嵌内容无需任何交互就能驱动系统浏览器打开任意 http(s) 页面，所以桌面端必须经用户确认；
 * 浏览器沿用自身的弹窗处理，直接开新标签页。
 */
import { isTauriEnvironment } from '@/lib/tauri';
import { isValidExternalUrl } from '@/lib/utils/urlUtils';
import { useExternalLinkConfirmStore } from '@/store/useExternalLinkConfirmStore';

/** Real links are far shorter; the prompt must show the address in full, so oversized ones are refused. */
const MAX_URL_LENGTH = 8192;

/** The request comes from untrusted content, so only a bounded prefix of it is ever logged. */
const LOGGED_URL_LENGTH = 200;

/**
 * Handles a link that embedded content asked the host to open. Only http(s) addresses qualify; in the desktop shell
 * the user is asked first, in a browser the link opens in a new tab.
 *
 * @param source Name of the requesting app, or null when the host cannot attribute the request.
 */
export function requestUntrustedLink(rawUrl: string, source: string | null): void {
  if (rawUrl.length > MAX_URL_LENGTH || !isValidExternalUrl(rawUrl)) {
    console.warn('[untrusted-link] Blocked external link request:', rawUrl.slice(0, LOGGED_URL_LENGTH));
    return;
  }

  // The normalized form (punycode host, resolved path) is exactly what the system browser receives.
  const url = new URL(rawUrl.trim()).href;
  if (isTauriEnvironment()) {
    useExternalLinkConfirmStore.getState().request({ url, source });
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}
