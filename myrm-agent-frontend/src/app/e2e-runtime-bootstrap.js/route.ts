/**
 * [INPUT]
 * - components/dev/e2e-runtime-bootstrap.js (POS: 把页面绑定到已校验的 E2E 私有后端的运行时绑定脚本)
 *
 * [OUTPUT]
 * GET /e2e-runtime-bootstrap.js — 非生产构建返回绑定脚本，生产构建返回 404
 *
 * [POS] 绑定脚本的开发期出口。脚本放在 `public/` 会原样进入桌面安装包与 Docker 镜像，所以它留在
 * `components/dev/`，只由这条路由提供；`process.env.NODE_ENV` 字面量让打包器在生产构建里删掉读文件的代码，
 * 产物里只剩一个返回 404 的处理器。脚本路径按进程工作目录解析：开发服务器都在前端项目根启动，
 * `i18n/load-messages.ts` 读语言包用的是同一约定。
 */
import { readFile } from 'node:fs/promises';
import path from 'node:path';

export async function GET(): Promise<Response> {
  if (process.env.NODE_ENV === 'production') {
    return new Response('Not Found', { status: 404 });
  }
  const script = await readFile(path.join(process.cwd(), 'src/components/dev/e2e-runtime-bootstrap.js'), 'utf-8');
  // 脚本随源码即改即用，不能被浏览器缓存成旧版本。
  return new Response(script, {
    headers: { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
