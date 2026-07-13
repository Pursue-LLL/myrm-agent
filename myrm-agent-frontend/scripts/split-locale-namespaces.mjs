#!/usr/bin/env node
/**
 * Split monolithic locales/{lang}.json into locales/namespaces/{lang}/ for lazy loading.
 * SSOT for translators remains locales/{lang}.json — run before dev/build/test.
 */

import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');
const languages = ['zh', 'en', 'ja', 'ko', 'de'];
const namespacesRoot = resolve(rootDir, 'locales/namespaces');
const manifestPath = resolve(namespacesRoot, 'manifest.json');

function writeJson(filePath, value) {
  mkdirSync(dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function splitLocale(lang, canonicalNamespaces, canonicalSettingsSections) {
  const sourcePath = resolve(rootDir, `locales/${lang}.json`);
  const messages = JSON.parse(readFileSync(sourcePath, 'utf-8'));
  const localeDir = resolve(namespacesRoot, lang);

  rmSync(localeDir, { recursive: true, force: true });
  mkdirSync(localeDir, { recursive: true });

  for (const namespace of canonicalNamespaces) {
    writeJson(resolve(localeDir, `${namespace}.json`), messages[namespace] ?? {});
  }

  const settingsDir = resolve(localeDir, 'settings');
  mkdirSync(settingsDir, { recursive: true });
  const settings = messages.settings ?? {};
  for (const section of canonicalSettingsSections) {
    writeJson(resolve(settingsDir, `${section}.json`), settings[section] ?? {});
  }
}

const zhMessages = JSON.parse(readFileSync(resolve(rootDir, 'locales/zh.json'), 'utf-8'));
const namespaces = Object.keys(zhMessages).filter((key) => key !== 'settings');
const settingsSections = Object.keys(zhMessages.settings ?? {});

for (const lang of languages) {
  splitLocale(lang, namespaces, settingsSections);
  console.log(`split locale namespaces: ${lang}`);
}

writeJson(manifestPath, {
  languages,
  namespaces: Object.keys(zhMessages),
  settingsSections,
});

console.log(`wrote ${manifestPath}`);
