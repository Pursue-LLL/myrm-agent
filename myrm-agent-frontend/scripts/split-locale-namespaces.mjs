#!/usr/bin/env node
/**
 * Split monolithic locales/{lang}.json into locales/namespaces/{lang}/ for lazy loading.
 * SSOT for translators remains locales/{lang}.json — run before dev/build/test.
 */

import { spawnSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');
const languages = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'];
const namespacesRoot = resolve(rootDir, 'locales/namespaces');
const manifestPath = resolve(namespacesRoot, 'manifest.json');

function writeJson(filePath, value) {
  mkdirSync(dirname(filePath), { recursive: true });
  try {
    if (existsSync(filePath)) {
      unlinkSync(filePath);
    }
  } catch {}
  writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

/** macOS/Windows: agent.json and Agent.json collide — encode mixed-case namespaces. */
function namespaceFilename(namespace) {
  if (namespace !== namespace.toLowerCase()) {
    return `@${namespace}.json`;
  }
  return `${namespace}.json`;
}

function resetDirectory(dirPath) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      rmSync(dirPath, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
      break;
    } catch (error) {
      if ((error?.code !== 'ENOTEMPTY' && error?.code !== 'EBUSY') || attempt === 4) {
        throw error;
      }
      try {
        execSync('sleep 0.1');
      } catch {
        // ignore
      }
    }
  }
  mkdirSync(dirPath, { recursive: true });
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

  resetDirectory(localeDir);

  for (const namespace of canonicalNamespaces) {
    writeJson(resolve(localeDir, namespaceFilename(namespace)), messages[namespace] ?? {});
  }

  const settingsDir = resolve(localeDir, 'settings');
  mkdirSync(settingsDir, { recursive: true });
  const settings = messages.settings ?? {};
  for (const section of canonicalSettingsSections) {
    const targetFile = resolve(settingsDir, `${section}.json`);
    mkdirSync(dirname(targetFile), { recursive: true });
    writeJson(targetFile, settings[section] ?? {});
  }
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
