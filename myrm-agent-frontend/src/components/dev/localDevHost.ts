/**
 * [INPUT]
 * - none (reads only `window.location.hostname`)
 *
 * [OUTPUT]
 * - isLocalDevHost: whether the page is served from a loopback host (`127.0.0.1` / `localhost`); false without a window
 *
 * [POS]
 * 开发桥的挂载守卫：所有 localhost 开发桥共用的主机判定。不依赖任何 store 或 lib，也独立于产品自己的主机判定，
 * 所以产品判定变宽不会让开发桥挂到更多主机上。
 */

export function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}
