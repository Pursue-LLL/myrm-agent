/**
 * [INPUT]
 * - none (reads only `process.env.NODE_ENV` and `window.location.hostname`)
 *
 * [OUTPUT]
 * - isLocalDevHost: whether the E2E test channel may be active: a non-production build served from a loopback host (`127.0.0.1` / `localhost`); false in a production build and without a window
 *
 * [POS]
 * 开发桥的挂载守卫：所有 localhost 开发桥，以及产品组件里挂 E2E 钩子的几处，共用的判定。生产构建恒为 false：桌面发行版同样
 * 从回环地址提供页面，主机名区分不了开发与发行。不依赖任何 store 或 lib，也独立于产品自己的主机判定，所以产品判定变宽
 * 不会让开发桥与 E2E 钩子挂到更多主机上。
 */

export function isLocalDevHost(): boolean {
  if (process.env.NODE_ENV === 'production' || typeof window === 'undefined') {
    return false;
  }
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}
