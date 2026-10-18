/**
 * 减少动态效果守卫的静态扫描：找出“自己产出一份 HTML 文档、并且带动画”的宿主，检查它是否自带
 * `@media (prefers-reduced-motion: reduce)` 守卫。
 *
 * 为什么需要：守卫是按文档生效的。主文档的 `globals.css` 只覆盖 Next 渲染的那一份文档；AI 生成的
 * widget、浏览器扩展 Side Panel、Tauri 自定义协议页各自是**独立文档**，宿主样式表不作用于它们，
 * 必须各自带守卫。这类缺口在 jsdom 与普通单测里都看不见（样式不参与断言），只能静态拦。
 *
 * 判定口径：
 * 1. 候选文件 = 含 `<style>` 或 `<html` 的源码（自己拼 HTML），或 `.css` 样式表（被某个独立文档引入）；
 * 2. 只对“带动画”的候选报警：有 `animation:`、`@keyframes` 或 Tailwind 的 `animate-*` 工具类；
 * 3. 该文件里必须出现 `prefers-reduced-motion`；
 * 4. 白名单按文件给出理由，理由同时写进 `temp-docs/roadmap/topic_09`，不允许无理由豁免。
 *
 * 为什么要扫 `animate-*`：预置模板只写 Tailwind 工具类，关键帧由 CDN 的样式表提供，本地没有任何
 * `@keyframes`。只看 `@keyframes` 会把这类宿主整批漏掉。
 */

/**
 * 自己产出 HTML 文档的源码：内联 `<style>`，或直接拼 `<!DOCTYPE html>` / `<html>`。
 *
 * 注意：React 组件的 `<style jsx>`（styled-jsx）渲染进 Next 的主文档，不算独立文档——主文档的
 * `globals.css` 守卫已经覆盖它，所以 `.tsx` / `.jsx` 不参与“拼文档”判定。
 */
const EMITS_HTML = /<style[\s>]|<html[\s>]|<!DOCTYPE html>/i;
/**
 * 动画来源：CSS 声明、关键帧，或 Tailwind 的 `animate-*` 工具类（含任意值写法 `animate-[...]`）。
 *
 * 为什么要算 `transition:`：过渡同样会连续重绘。`transition: all` 加一处 `:hover { transform: ... }`
 * 就是一段真实的位移动画（`crypto_packager.py` 的生成页就是这样）；只盯 `animation` / `@keyframes`
 * 会把这类独立文档整批漏掉。
 */
const HAS_MOTION = /@keyframes|\banimation\s*:|\btransition\s*:|\banimate-[\w[]/;
const HAS_GUARD = /prefers-reduced-motion/;
/**
 * 守卫必须落到通用选择器上，而不是只关掉一两个具名动画。
 *
 * 为什么单独判：文件里只要出现 `prefers-reduced-motion` 就算通过的话，`globals.css` 里那两处
 * 只管 `.animate-node-pulse` 与品牌按钮的窄补丁也能满足它——而真正的缺口正是“其余动画没人管”
 * （`BUG-AGENT-2026-10-18-002` 的起点）。允许换行与任意空白。
 */
const UNIVERSAL_GUARD = /\*\s*,\s*\*::before\s*,\s*\*::after\s*\{/;

/** 视为“样式表”的扩展名：它们本身不是文档，但会被某个独立文档引入。 */
const STYLESHEET_EXTENSIONS = new Set(['.css']);
/**
 * 可能自拼 HTML 文档的源码扩展名。刻意不含 `.tsx` / `.jsx`：React 组件的样式最终渲染进 Next
 * 主文档，由 `globals.css` 的守卫覆盖，不需要自带。
 */
const SOURCE_EXTENSIONS = new Set(['.ts', '.mjs', '.js', '.rs', '.py', '.html']);

export interface ReducedMotionSurface {
  /** 相对仓库根的路径。 */
  path: string;
  /** 命中的动画片段（首条），便于在报错里定位。 */
  evidence: string;
}

function firstMotionEvidence(source: string): string | undefined {
  const match =
    /@keyframes\s+[\w-]+|\banimation\s*:[^;]{0,60}|\btransition\s*:[^;]{0,60}|\banimate-[\w[\]-]{0,40}/.exec(source);
  return match?.[0];
}

/**
 * 只保留“真正会进入文档的代码”，丢掉测试模块。
 *
 * 为什么必须剥：Rust 的宿主文件常在同一个文件里写单测，而单测会断言守卫字符串存在
 * （`assert!(html.contains("@media (prefers-reduced-motion: reduce)"))`）。若不剥掉测试段，
 * 把真正的守卫删了，扫描器仍会从断言里读到关键字，从而漏报——这是实测出来的假阴性。
 */
function stripTestRegions(path: string, source: string): string {
  const dot = path.lastIndexOf('.');
  const extension = dot === -1 ? '' : path.slice(dot);
  if (extension === '.rs') {
    // Rust 的测试模块惯例是文件末尾的 `#[cfg(test)] mod tests { ... }`。
    const index = source.indexOf('#[cfg(test)]');
    return index === -1 ? source : source.slice(0, index);
  }
  if (extension === '.py') {
    // Python 测试常放在同目录 tests/ 下，不在此文件内；但内联 `if __name__ == "__main__"` 之后的
    // 自检代码同样不该被当成生产样式，保守起见一并剥掉。
    const index = source.indexOf('if __name__ ==');
    return index === -1 ? source : source.slice(0, index);
  }
  return source;
}

/**
 * 判断单个文件是否需要自带守卫。返回 `undefined` 表示不适用（不是 HTML 宿主，或不带动画）。
 * 纯函数，无 IO，便于单测。
 */
export function findUnguardedMotionSurface(path: string, source: string): ReducedMotionSurface | undefined {
  const dot = path.lastIndexOf('.');
  const extension = dot === -1 ? '' : path.slice(dot);
  const isStylesheet = STYLESHEET_EXTENSIONS.has(extension);
  const isSource = SOURCE_EXTENSIONS.has(extension);
  if (!isStylesheet && !isSource) {
    return undefined;
  }
  const production = stripTestRegions(path, source);
  // 样式表只看自身；源码还要求它真的在拼 HTML 文档，否则像 `foo.ts` 里写个 animate 类名不算宿主。
  if (!isStylesheet && !EMITS_HTML.test(production)) {
    return undefined;
  }
  if (!HAS_MOTION.test(production)) {
    return undefined;
  }
  // 守卫要“真的兜住全部动画”：既出现在 reduce 媒体查询里，又落在通用选择器上。
  if (HAS_GUARD.test(production) && UNIVERSAL_GUARD.test(production)) {
    return undefined;
  }
  const evidence = firstMotionEvidence(production);
  if (evidence === undefined) {
    return undefined;
  }
  return { path, evidence };
}

/** 白名单：文件 → 不注入守卫的具体理由。理由必须在 roadmap 里有对应记录。 */
export const ALLOWED_WITHOUT_GUARD: Readonly<Record<string, string>> = {
  'myrm-agent-server/app/api/webui/router.py':
    '欢迎页只有一次性的 0.5s fadeIn，不是循环动画；且它只在本地启动引导时出现一次',
  'myrm-agent-server/app/services/artifacts/delight_showcase/catalog.py':
    '8 个预置模板中 5 个用 canvas + requestAnimationFrame 绘制，CSS 守卫对 canvas 无效；' +
    '且这些模板的交付物本身就是动画（烟花、流星雨、转盘、弹球、波浪），属用户要的结果，不由宿主强加',
};

/**
 * 汇总一次扫描结果：`surfaces` 为需要守卫却缺失的文件，`allowlisted` 为命中白名单的文件，
 * `scanned` 为参与判定的候选文件数（用于反向自检，避免路径失效后静默通过）。
 */
export interface ReducedMotionScanReport {
  violations: ReducedMotionSurface[];
  allowlisted: ReducedMotionSurface[];
  scanned: number;
}

export function scanReducedMotionSurfaces(files: Iterable<{ path: string; source: string }>): ReducedMotionScanReport {
  const violations: ReducedMotionSurface[] = [];
  const allowlisted: ReducedMotionSurface[] = [];
  let scanned = 0;
  for (const { path, source } of files) {
    scanned += 1;
    const surface = findUnguardedMotionSurface(path, source);
    if (surface === undefined) {
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(ALLOWED_WITHOUT_GUARD, surface.path)) {
      allowlisted.push(surface);
    } else {
      violations.push(surface);
    }
  }
  return { violations, allowlisted, scanned };
}
