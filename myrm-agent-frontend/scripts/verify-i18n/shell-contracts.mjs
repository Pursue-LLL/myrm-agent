/**
 * [INPUT] src/i18n/locale-manifest.ts (POS: deferred namespace 清单 SSOT) + SSR 首屏 shell 组件源码 + scripts/scan-home-i18n-shell.mjs
 * [OUTPUT] verifyShellDeferredNamespaceGate / verifyHomeRouteShellContract
 * [POS] verify-i18n 的首屏 shell 契约检查（验证 8 及其前置门禁）：首屏渲染的组件只能引用随 shell 下发的命名空间，否则 chat 首屏 MISSING_MESSAGE。
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { execSync } from 'node:child_process';
import { resolve, join } from 'path';

/** App-shell TSX files that render on first paint and must not use deferred i18n namespaces. */
const SSR_SHELL_I18N_SCAN_ROOTS = [
  'src/components/layout',
  'src/components/features/chat-window/ChatWindow.tsx',
  'src/components/features/chat-window/EmptyChat.tsx',
];

const USE_TRANSLATIONS_NS_RE = /useTranslations\s*\(\s*['"]([^'"]+)['"]\s*\)/g;

function collectTsxFiles(dirPath, out) {
  for (const entry of readdirSync(dirPath)) {
    const fullPath = join(dirPath, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      collectTsxFiles(fullPath, out);
    } else if (entry.endsWith('.tsx')) {
      out.push(fullPath);
    }
  }
}

function readDeferredNamespaces(rootDir) {
  const manifestPath = resolve(rootDir, 'src/i18n/locale-manifest.ts');
  const source = readFileSync(manifestPath, 'utf-8');
  const blockMatch = source.match(/DEFERRED_NAMESPACES\s*=\s*\[([\s\S]*?)\]\s*as\s*const/);
  if (!blockMatch) {
    throw new Error('Could not parse DEFERRED_NAMESPACES from locale-manifest.ts');
  }
  return [...blockMatch[1].matchAll(/['"]([^'"]+)['"]/g)].map((match) => match[1]);
}

export function verifyShellDeferredNamespaceGate(ctx) {
  const { rootDir } = ctx;
  console.log('📋 验证 SSR shell 组件未引用 deferred i18n namespace...');
  const deferredNamespaces = new Set(readDeferredNamespaces(rootDir));
  const shellFiles = [];

  for (const relativePath of SSR_SHELL_I18N_SCAN_ROOTS) {
    const absolutePath = resolve(rootDir, relativePath);
    if (statSync(absolutePath).isDirectory()) {
      collectTsxFiles(absolutePath, shellFiles);
    } else {
      shellFiles.push(absolutePath);
    }
  }

  let shellErrors = 0;
  for (const filePath of shellFiles) {
    const source = readFileSync(filePath, 'utf-8');
    for (const match of source.matchAll(USE_TRANSLATIONS_NS_RE)) {
      const namespace = match[1].split('.')[0];
      if (deferredNamespaces.has(namespace)) {
        console.error(
          `  ❌ ${filePath.replace(`${rootDir}/`, '')} uses useTranslations('${match[1]}') but '${namespace}' is deferred`,
        );
        shellErrors += 1;
        ctx.hasErrors = true;
      }
    }
  }

  if (shellErrors === 0) {
    console.log(
      `  ✅ SSR shell 扫描通过（${shellFiles.length} 个文件，deferred: ${[...deferredNamespaces].join(', ') || '(none)'}）`,
    );
  }
}

// 验证8: home-route settings i18n shell contract（防 chat 首屏 MISSING_MESSAGE）
export function verifyHomeRouteShellContract(ctx) {
  console.log('\n📋 验证 home-route settings i18n shell contract...');
  try {
    execSync(`"${process.execPath}" scripts/scan-home-i18n-shell.mjs`, { stdio: 'inherit', cwd: ctx.rootDir });
    console.log('  ✅ home-route settings shell contract 通过');
  } catch {
    ctx.hasErrors = true;
  }
}
