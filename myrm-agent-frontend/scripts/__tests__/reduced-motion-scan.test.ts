/**
 * [INPUT]
 * 由测试构造的“文件路径 + 文件内容”对。
 * [OUTPUT]
 * Vitest: 独立文档宿主的判定口径——什么算宿主、什么算已覆盖、什么必须报警。
 * [POS]
 * `verify:reduced-motion` 门禁的判定规则单测。它守的是一条按文档生效的无障碍契约：
 * 主文档的 `globals.css` 覆盖不到 AI 生成 widget、扩展 Side Panel、Tauri 自定义协议页这些独立文档。
 */
import { describe, expect, it } from 'vitest';

import { ALLOWED_WITHOUT_GUARD, findUnguardedMotionSurface, scanReducedMotionSurfaces } from '../reduced-motion-scan';

const GUARD =
  '@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; } }';

describe('findUnguardedMotionSurface', () => {
  it('flags a stylesheet that animates without a universal guard', () => {
    const surface = findUnguardedMotionSurface('ext/sidepanel.css', '.a { animation: pulse 1s infinite; }');
    expect(surface?.evidence).toContain('animation');
  });

  it('accepts the same stylesheet once it carries the universal guard', () => {
    const source = `.a { animation: pulse 1s infinite; }\n${GUARD}`;
    expect(findUnguardedMotionSurface('ext/sidepanel.css', source)).toBeUndefined();
  });

  // 这一条钉的是 BUG-AGENT-2026-10-18-002 的起点：只关一两个具名动画不算兜住全部。
  it('rejects a narrow guard that only disables one named animation', () => {
    const source = `.a { animation: pulse 1s infinite; }
@media (prefers-reduced-motion: reduce) { .a { animation: none; } }`;
    expect(findUnguardedMotionSurface('ext/sidepanel.css', source)?.path).toBe('ext/sidepanel.css');
  });

  it('flags a source file that builds its own HTML document with motion', () => {
    const source = 'const html = `<html><style>@keyframes pulse {}</style></html>`;';
    expect(findUnguardedMotionSurface('app/page.py', source)?.path).toBe('app/page.py');
  });

  // Tailwind 工具类不写本地 @keyframes（关键帧由 CDN 提供），只看 @keyframes 会整批漏掉。
  it('treats an animate-* utility class as motion, even with no local keyframes', () => {
    const source = 'const html = `<html><div class="animate-pulse"></div></html>`;';
    expect(findUnguardedMotionSurface('svc/catalog.py', source)?.evidence).toBe('animate-pulse');
  });

  // React 组件的 <style jsx> 渲染进 Next 的主文档，由 globals.css 覆盖，不该被当成独立文档。
  it('ignores a .tsx component: its styled-jsx lands in the main document', () => {
    const source = 'export const A = () => <div><style jsx>{`@keyframes x {}`}</style></div>;';
    expect(findUnguardedMotionSurface('src/a.tsx', source)).toBeUndefined();
  });

  // 过渡同样连续重绘：`transition: all` 配一处 `:hover { transform: ... }` 就是真实位移动画
  // （`crypto_packager.py` 的生成页就是这样）。只盯 animation / @keyframes 会整批漏掉。
  it('treats a transition as motion, so a transition-only document is covered too', () => {
    const source = 'const h = `<html><style>.a{transition: background .2s} .a:hover{background:red}</style></html>`;';
    expect(findUnguardedMotionSurface('svc/page.py', source)?.evidence).toContain('transition');
  });

  it('ignores a file with no motion at all', () => {
    expect(findUnguardedMotionSurface('ext/static.css', '.a { color: red; }')).toBeUndefined();
  });

  // 实测出来的假阴性：Rust 宿主文件里的单测会断言守卫字符串存在，若不剥掉测试段，
  // 删掉真正的 CSS 守卫后扫描器仍能从断言里读到关键字，从而静默通过。
  it('does not count a guard that only appears inside the Rust test module', () => {
    const source = `fn page() -> String {
    format!(r#"<html><style>.dot {{ animation: pulse 2s infinite; }}</style></html>"#)
}

#[cfg(test)]
mod tests {
    #[test]
    fn carries_guard() {
        assert!(page().contains("@media (prefers-reduced-motion: reduce)"));
    }
}`;
    expect(findUnguardedMotionSurface('src/curtain.rs', source)?.path).toBe('src/curtain.rs');
  });

  it('accepts the same Rust file once the guard moves into the page markup', () => {
    const source = `fn page() -> String {
    format!(r#"<html><style>
      .dot {{ animation: pulse 2s infinite; }}
      @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation-duration: 0.01ms !important; }} }}
    </style></html>"#)
}

#[cfg(test)]
mod tests {
    #[test]
    fn carries_guard() {
        assert!(page().contains("@media (prefers-reduced-motion: reduce)"));
    }
}`;
    expect(findUnguardedMotionSurface('src/curtain.rs', source)).toBeUndefined();
  });
});

describe('scanReducedMotionSurfaces', () => {
  it('separates violations from allowlisted surfaces and counts what it scanned', () => {
    const report = scanReducedMotionSurfaces([
      { path: 'ext/ok.css', source: `.a { animation: p 1s infinite; } ${GUARD}` },
      { path: 'ext/bad.css', source: '.a { animation: p 1s infinite; }' },
      { path: 'plain.css', source: '.a { color: red; }' },
    ]);

    expect(report.scanned).toBe(3);
    expect(report.violations.map((item) => item.path)).toEqual(['ext/bad.css']);
    expect(report.allowlisted).toEqual([]);
  });

  it('keeps the documented exceptions out of the violation list', () => {
    const [path, reason] = Object.entries(ALLOWED_WITHOUT_GUARD)[0];
    expect(reason.length).toBeGreaterThan(0);

    const report = scanReducedMotionSurfaces([
      { path, source: 'const html = `<html><div class="animate-pulse"></div></html>`;' },
    ]);

    expect(report.violations).toEqual([]);
    expect(report.allowlisted.map((item) => item.path)).toEqual([path]);
  });
});
