#!/usr/bin/env node
/**
 * Split monolithic locales/{lang}.json into locales/namespaces/{lang}/ for lazy loading.
 * SSOT for translators remains locales/{lang}.json — run before dev/build/test.
 */

import { spawnSync } from 'child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');
const languages = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'];
const namespacesRoot = resolve(rootDir, 'locales/namespaces');
const manifestPath = resolve(namespacesRoot, 'manifest.json');

/**
 * Concurrent readers (dev server, vitest, other sessions) must never observe a missing or
 * half-written namespace file, so files are replaced via same-dir rename and only
 * stale entries are pruned afterwards — the locale directory is never wiped.
 */
function writeJson(filePath, value) {
  mkdirSync(dirname(filePath), { recursive: true });
  const next = `${JSON.stringify(value, null, 2)}\n`;
  if (existsSync(filePath) && readFileSync(filePath, 'utf-8') === next) {
    return;
  }
  const tmpPath = `${filePath}.${process.pid}.tmp`;
  writeFileSync(tmpPath, next, 'utf-8');
  renameSync(tmpPath, filePath);
}

/** macOS/Windows: agent.json and Agent.json collide — encode mixed-case namespaces. */
function namespaceFilename(namespace) {
  if (namespace !== namespace.toLowerCase()) {
    return `@${namespace}.json`;
  }
  return `${namespace}.json`;
}

/** Remove files/dirs under `dirPath` that are not in `keep` (in-flight `.tmp` files of peers are left alone). */
function pruneStale(dirPath, keep) {
  for (const entry of readdirSync(dirPath)) {
    if (!keep.has(entry) && !entry.endsWith('.tmp')) {
      rmSync(resolve(dirPath, entry), { recursive: true, force: true });
    }
  }
}

function tryParseJson(filePath) {
  if (!existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  } catch {
    return null;
  }
}

function ensureMonolithLocales() {
  const zhPath = resolve(rootDir, 'locales/zh.json');
  if (tryParseJson(zhPath) !== null) {
    return;
  }
  if (!existsSync(manifestPath)) {
    throw new Error(
      'locales/zh.json is invalid and locales/namespaces/manifest.json is missing — '
        + 'restore locale files or run: node scripts/merge-locale-namespaces.mjs',
    );
  }
  const mergeScript = resolve(__dirname, 'merge-locale-namespaces.mjs');
  const result = spawnSync(process.execPath, [mergeScript], {
    cwd: rootDir,
    stdio: 'inherit',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function loadCanonicalSchema() {
  const zhMessages = tryParseJson(resolve(rootDir, 'locales/zh.json'));
  if (zhMessages !== null) {
    return {
      namespaces: Object.keys(zhMessages).filter((key) => key !== 'settings'),
      settingsSections: Object.keys(zhMessages.settings ?? {}),
      manifestNamespaces: Object.keys(zhMessages),
    };
  }
  const manifest = tryParseJson(manifestPath);
  if (manifest?.namespaces && manifest?.settingsSections) {
    return {
      namespaces: manifest.namespaces.filter((key) => key !== 'settings'),
      settingsSections: manifest.settingsSections,
      manifestNamespaces: manifest.namespaces,
    };
  }
  throw new Error('locales/zh.json is invalid and manifest.json is unavailable');
}

function splitLocale(lang, canonicalNamespaces, canonicalSettingsSections) {
  let sourcePath = resolve(rootDir, `locales/${lang}.json`);
  if (!existsSync(sourcePath) && lang === 'zh-TW') {
    sourcePath = resolve(rootDir, 'locales/zh.json');
  }
  let messages = tryParseJson(sourcePath);
  if (messages === null) {
    ensureMonolithLocales();
    messages = tryParseJson(sourcePath);
  }
  if (messages === null) {
    throw new Error(`Failed to parse locale source: ${sourcePath}`);
  }
  const localeDir = resolve(namespacesRoot, lang);
  mkdirSync(localeDir, { recursive: true });

  const namespaceFiles = canonicalNamespaces.map(namespaceFilename);
  canonicalNamespaces.forEach((namespace, index) => {
    writeJson(resolve(localeDir, namespaceFiles[index]), messages[namespace] ?? {});
  });

  const settingsDir = resolve(localeDir, 'settings');
  mkdirSync(settingsDir, { recursive: true });
  const settings = messages.settings ?? {};
  for (const section of canonicalSettingsSections) {
    const targetFile = resolve(settingsDir, `${section}.json`);
    writeJson(targetFile, settings[section] ?? {});
  }

  pruneStale(localeDir, new Set([...namespaceFiles, 'settings']));
  pruneStale(settingsDir, new Set(canonicalSettingsSections.map((section) => `${section}.json`)));
}

ensureMonolithLocales();
const { namespaces, settingsSections, manifestNamespaces } = loadCanonicalSchema();

for (const lang of languages) {
  splitLocale(lang, namespaces, settingsSections);
  console.log(`split locale namespaces: ${lang}`);
}

writeJson(manifestPath, {
  languages,
  namespaces: manifestNamespaces,
  settingsSections,
});

console.log(`wrote ${manifestPath}`);
