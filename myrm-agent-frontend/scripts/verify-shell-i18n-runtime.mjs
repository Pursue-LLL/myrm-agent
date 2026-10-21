#!/usr/bin/env node
/**
 * Runtime verification: SSR shell includes chat-critical settings i18n;
 * deferred endpoint excludes shell sections; no MISSING_MESSAGE in HTML.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const baseUrl = process.env.WEBUI_URL ?? 'http://127.0.0.1:3000';
const manifestSourcePath = resolve(process.cwd(), 'src/i18n/locale-manifest.ts');

function readShellSettingsSections() {
  const source = readFileSync(manifestSourcePath, 'utf-8');
  const match = source.match(/SSR_SHELL_SETTINGS_SECTIONS = \[([\s\S]*?)\] as const/);
  if (!match) {
    throw new Error('Could not parse SSR_SHELL_SETTINGS_SECTIONS from locale-manifest.ts');
  }

  return [...match[1].matchAll(/'([^']+)'/g)].map((item) => item[1]);
}

const shellSections = readShellSettingsSections();

const localeExpectations = {
  zh: { text: '搜索模型', cookie: 'zh' },
  en: { text: 'Search models', cookie: 'en' },
};

let failed = 0;

function fail(msg) {
  console.error(`❌ ${msg}`);
  failed += 1;
}

function pass(msg) {
  console.log(`✅ ${msg}`);
}

async function fetchText(path, cookie) {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: cookie ? { Cookie: `NEXT_LOCALE=${cookie}` } : {},
  });
  if (!res.ok) {
    throw new Error(`${path} returned ${res.status}`);
  }
  return res.text();
}

console.log(`🔍 verify shell i18n runtime @ ${baseUrl}\n`);

for (const [locale, { text, cookie }] of Object.entries(localeExpectations)) {
  const html = await fetchText('/', cookie);
  if (html.includes('MISSING_MESSAGE')) {
    fail(`${locale}: HTML contains MISSING_MESSAGE`);
  } else {
    pass(`${locale}: no MISSING_MESSAGE in SSR HTML`);
  }
  if (!html.includes('showSidebar')) {
    fail(`${locale}: layout.showSidebar key not embedded in SSR HTML`);
  } else {
    pass(`${locale}: layout.showSidebar embedded in SSR HTML`);
  }
  if (!html.includes('primaryModel') || !html.includes('searchModels')) {
    fail(`${locale}: defaultModel keys not embedded in SSR HTML`);
  } else {
    pass(`${locale}: defaultModel keys embedded in SSR HTML`);
  }
  if (!html.includes(text)) {
    fail(`${locale}: expected translated text "${text}" not found in HTML`);
  } else {
    pass(`${locale}: translated search placeholder present`);
  }
}

const deferred = JSON.parse(await fetchText('/api/i18n/deferred', 'zh'));
const overlap = shellSections.filter((section) => section in (deferred.settings ?? {}));
if (overlap.length > 0) {
  fail(`deferred overlaps shell sections: ${overlap.join(', ')}`);
} else {
  pass('deferred API excludes all SSR shell settings sections');
}

const manifestPath = resolve(process.cwd(), 'locales/namespaces/manifest.json');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
const deferredFromManifest = manifest.settingsSections.filter((s) => !shellSections.includes(s));
if (deferredFromManifest.length !== Object.keys(deferred.settings ?? {}).length) {
  fail(
    `deferred section count mismatch: api=${Object.keys(deferred.settings ?? {}).length} manifest=${deferredFromManifest.length}`,
  );
} else {
  pass(`deferred serves ${deferredFromManifest.length} settings sections`);
}

console.log('\n' + '='.repeat(50));
if (failed > 0) {
  console.error(`❌ ${failed} check(s) failed`);
  process.exit(1);
}
console.log('✅ All runtime shell i18n checks passed');
