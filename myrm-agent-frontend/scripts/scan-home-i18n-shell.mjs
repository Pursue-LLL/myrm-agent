#!/usr/bin/env node
/**
 * Ensures home-route components only reference settings sections present in SSR shell.
 * Prevents MISSING_MESSAGE regressions after locale namespace split.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const rootDir = join(process.cwd());
const manifestPath = join(rootDir, 'src/i18n/locale-manifest.ts');
const scanRoots = [
  'src/components/features/chat-window',
  'src/components/features/app-shell',
  'src/components/features/message-input-actions',
  'src/components/layout',
  'src/hooks/useAgentConfigPanel.ts',
  'src/hooks/use-agent-config-panel',
];

function readShellSettingsSections() {
  const source = readFileSync(manifestPath, 'utf-8');
  const match = source.match(/SSR_SHELL_SETTINGS_SECTIONS = \[([\s\S]*?)\] as const/);
  if (!match) {
    throw new Error('Could not parse SSR_SHELL_SETTINGS_SECTIONS from locale-manifest.ts');
  }

  return [...match[1].matchAll(/'([^']+)'/g)].map((item) => item[1]);
}

function collectSourceFiles(entryPath) {
  const absolute = join(rootDir, entryPath);
  const stats = statSync(absolute);
  if (stats.isFile() && /\.(tsx|ts)$/.test(absolute)) {
    return [absolute];
  }
  if (!stats.isDirectory()) {
    return [];
  }

  const files = [];
  for (const name of readdirSync(absolute)) {
    if (name.includes('__tests__') || name.includes('.test.')) {
      continue;
    }
    files.push(...collectSourceFiles(join(entryPath, name)));
  }
  return files;
}

function scanFile(filePath, shellSections) {
  const content = readFileSync(filePath, 'utf-8');
  const violations = [];
  const pattern = /useTranslations\(\s*['"]settings\.([^'"]+)['"]\s*\)/g;

  for (const match of content.matchAll(pattern)) {
    const section = match[1].split('.')[0];
    if (!shellSections.includes(section)) {
      violations.push({
        file: relative(rootDir, filePath),
        section,
      });
    }
  }

  return violations;
}

const shellSections = readShellSettingsSections();
const files = scanRoots.flatMap((entry) => collectSourceFiles(entry));
const violations = files.flatMap((file) => scanFile(file, shellSections));

if (violations.length > 0) {
  console.error('❌ Home-route settings i18n shell contract violations:');
  for (const violation of violations) {
    console.error(`   - ${violation.file}: settings.${violation.section} not in SSR shell`);
  }
  process.exit(1);
}

console.log(`✅ Home-route settings i18n shell contract OK (${shellSections.length} shell sections, ${files.length} files scanned)`);
