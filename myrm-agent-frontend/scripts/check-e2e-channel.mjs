#!/usr/bin/env node
/**
 * E2E 测试通道门禁（零容忍）：产品代码里的 E2E 钩子只能存在于非生产构建。
 *
 * 背景：桌面发行版从回环地址 `http://127.0.0.1:<port>` 提供页面，与本地开发同一主机名，所以主机判定拦不住
 * 测试通道；再叠加 `window.name` 这个任意跨源页面都能写入的绑定信任根，发行版里的 E2E 桥就是一扇可被外部
 * 页面推开的门。守卫必须是构建期常量 `process.env.NODE_ENV`，打包器据此把整段分支连同字符串一起删掉。
 * 判定规则见 `e2e-channel-scan.ts`。
 *
 * 三条规则。规则 1、2 的范围是 `src/` 下 `components/dev/` 之外的非测试文件（规则 1 另含开发桥目录里的加载器）：
 * 1. 每一处通道引用（`window.__MYRM_*` / `__myrm*` 句柄及其在对象字面量、解构里的写法、`e2e_*` 存储键、
 *    `myrm-e2e-*` 事件、`e2e-runtime-bootstrap` 脚本 id 与地址、`/…/test/…` 测试接口路径、开发桥组件的 JSX 挂载）
 *    都必须落在非生产守卫之后；
 * 2. 产品代码只能导入开发桥目录的叶子模块 `localDevHost`，以及下面两处挂载点对各自桥组件的导入；
 * 3. `public/` 下的静态资源（脚本、页面、清单）里不得出现任何通道标识：静态资源不经打包器，整份原样进入桌面
 *    安装包与 Docker 镜像，没有守卫可言。测试专用脚本放在 `src/components/dev/`，由开发期路由提供。
 *
 * 反向自检：扫描到的源文件或静态资源数为 0、或守卫之后的引用数低于下限时直接失败——路径或识别规则失效必须暴露，
 * 而不是静默通过。
 *
 * 运行：bun scripts/check-e2e-channel.mjs
 * 退出码：0 = 产品代码里没有无守卫的测试通道；1 = 存在 / 自检失败
 */

import { readFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findChannelTextLines, findDevBridgeImports, scanE2eChannelSites } from './e2e-channel-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = resolve(rootDir, 'src');
const publicDir = resolve(rootDir, 'public');
const devBridgeDir = resolve(srcDir, 'components', 'dev') + sep;
/** `public/` 里会被浏览器当文本执行或解析的资源；图片等二进制不含标识。 */
const PUBLIC_TEXT_EXTENSIONS = new Set(['.js', '.mjs', '.html', '.json']);

/** 开发桥组件的挂载点：文件 → 它被允许导入的开发桥模块。挂载处是否受守卫由规则 1 判定。 */
const BRIDGE_MOUNTS = new Map([
  ['src/app/layout.tsx', new Set(['@/components/dev/E2eBridgeLoader'])],
  ['src/components/layout/AppLayout.tsx', new Set(['@/components/dev/E2ECompanionBridge'])],
]);
/**
 * 开发桥目录里唯一把各桥静态导入进来的文件：各桥进不进生产包，取决于它渲染各桥时的守卫，所以它和产品文件一样受规则 1 约束。
 * 目录里其余文件本身就是测试通道，不在扫描范围内。
 */
const GUARDED_DEV_BRIDGE_FILES = new Set(['src/components/dev/E2eBridgeLoader.tsx']);
/** 自检下限：现有受守卫的通道引用数远高于它；低于它说明识别规则或扫描范围失效。 */
const MIN_GUARDED_SITES = 40;

let scanned = 0;
let guardedSites = 0;
let publicScanned = 0;
const unguarded = [];
const strayImports = [];
const publicLeaks = [];
for (const file of walkSourceFiles(srcDir, new Set(['.ts', '.tsx']))) {
  const path = relative(rootDir, file).split(sep).join('/');
  const inDevBridgeDir = file.startsWith(devBridgeDir);
  if (inDevBridgeDir && !GUARDED_DEV_BRIDGE_FILES.has(path)) {
    continue;
  }
  scanned += 1;
  const source = readFileSync(file, 'utf-8');
  for (const site of scanE2eChannelSites(source, path)) {
    if (site.guarded) {
      guardedSites += 1;
    } else {
      unguarded.push(`  ${path}:${site.line}  ${site.kind}  ${site.name}`);
    }
  }
  if (inDevBridgeDir) {
    continue;
  }
  const allowedImports = BRIDGE_MOUNTS.get(path) ?? new Set();
  for (const specifier of findDevBridgeImports(source, path)) {
    if (!allowedImports.has(specifier)) {
      strayImports.push(`  ${path}  ${specifier}`);
    }
  }
}

for (const file of walkSourceFiles(publicDir, PUBLIC_TEXT_EXTENSIONS)) {
  publicScanned += 1;
  const path = relative(rootDir, file).split(sep).join('/');
  for (const line of findChannelTextLines(readFileSync(file, 'utf-8'))) {
    publicLeaks.push(`  ${path}:${line}`);
  }
}

if (scanned === 0 || publicScanned === 0) {
  console.error('[e2e-channel] 自检失败：未找到任何源文件或静态资源，路径可能已失效——拒绝静默通过。');
  process.exit(1);
}
if (guardedSites < MIN_GUARDED_SITES) {
  console.error(
    `[e2e-channel] 自检失败：只识别到 ${guardedSites} 处受守卫的通道引用（下限 ${MIN_GUARDED_SITES}），识别规则或扫描范围可能已失效——拒绝静默通过。`,
  );
  process.exit(1);
}
if (unguarded.length > 0) {
  console.error(`[e2e-channel] ${unguarded.length} 处 E2E 测试通道引用没有站在「非生产构建」守卫之后：`);
  console.error(unguarded.join('\n'));
  console.error(
    "\n把引用放进 `if (process.env.NODE_ENV !== 'production') { … }`，或在函数开头 `if (process.env.NODE_ENV === 'production') { return … }`。" +
      '\n必须直接写 `process.env.NODE_ENV` 字面量：打包器只对它做死代码删除，包一层常量或函数不保证被折叠。',
  );
}
if (strayImports.length > 0) {
  console.error(`[e2e-channel] ${strayImports.length} 处产品代码导入了开发桥目录里不该被产品依赖的模块：`);
  console.error(strayImports.join('\n'));
  console.error('\n产品代码只能导入 `localDevHost`；桥组件只在 BRIDGE_MOUNTS 列出的挂载点导入，且挂载处要受守卫。');
}
if (publicLeaks.length > 0) {
  console.error(`[e2e-channel] ${publicLeaks.length} 处 \`public/\` 静态资源里出现了 E2E 测试通道标识：`);
  console.error(publicLeaks.join('\n'));
  console.error(
    '\n`public/` 不经打包器，整份原样进入桌面安装包与 Docker 镜像，没有守卫可言。' +
      '\n测试专用脚本放进 `src/components/dev/`，由开发期路由提供（生产构建里该路由返回 404）。',
  );
}
if (unguarded.length > 0 || strayImports.length > 0 || publicLeaks.length > 0) {
  process.exit(1);
}
console.log(
  `[e2e-channel] OK：扫描 ${scanned} 个源文件，${guardedSites} 处 E2E 测试通道引用都在非生产守卫之后，开发桥只在挂载点被导入；` +
    `${publicScanned} 个静态资源里没有测试通道标识。`,
);
