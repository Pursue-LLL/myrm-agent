#!/usr/bin/env node
/** Rebuild monolithic locales/{lang}.json from locales/namespaces/{lang}/ (inverse of split). */

import { existsSync, readFileSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');
const namespacesRoot = resolve(rootDir, 'locales/namespaces');
const manifest = JSON.parse(readFileSync(resolve(namespacesRoot, 'manifest.json'), 'utf-8'));

function namespaceFilename(namespace) {
  if (namespace !== namespace.toLowerCase()) {
    return `@${namespace}.json`;
  }
  return `${namespace}.json`;
}

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

function mergeLocale(lang) {
  const localeDir = resolve(namespacesRoot, lang);
  const messages = {};

  for (const namespace of manifest.namespaces) {
    if (namespace === 'settings') {
      continue;
    }
    const filePath = resolve(localeDir, namespaceFilename(namespace));
    messages[namespace] = existsSync(filePath) ? readJson(filePath) : {};
  }

  const settingsDir = resolve(localeDir, 'settings');
  const settings = {};
  for (const section of manifest.settingsSections) {
    const filePath = resolve(settingsDir, `${section}.json`);
    settings[section] = existsSync(filePath) ? readJson(filePath) : {};
  }
  messages.settings = settings;

  const outPath = resolve(rootDir, `locales/${lang}.json`);
  writeFileSync(outPath, `${JSON.stringify(messages, null, 2)}\n`, 'utf-8');
  console.log(`merged ${lang} -> ${outPath}`);
}

for (const lang of manifest.languages) {
  mergeLocale(lang);
}
