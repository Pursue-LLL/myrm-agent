/**
 * Proxy address check shared by the forms that take a forward proxy.
 *
 * [INPUT] none
 * [OUTPUT] isProxyUrlInvalid: true for a non-blank value that is not an http, https, socks5 or socks5h URL
 * [POS] Pure client-side shape check so a form can flag a typo before any request; the server applies the
 *       authoritative rules (supported schemes, blocked targets) when the value is used.
 */

const PROXY_URL_PATTERN = /^(https?|socks5h?):\/\/\S+$/i;

export function isProxyUrlInvalid(proxy: string | undefined): boolean {
  const value = proxy?.trim() ?? '';
  return value !== '' && !PROXY_URL_PATTERN.test(value);
}
