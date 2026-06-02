#!/usr/bin/env node
/**
 * 翻译完整性验证脚本
 *
 * - metadata.settingsTabs / settings.menu / settings.developer
 * - zh.json 与 en.json 全量 key 树一致
 * - agent.configPanel 下关键 string 键在 zh/en/ja/ko/de 均存在（防 MISSING_MESSAGE）
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, '..');

// 有效的tabs列表（必须与 app/settings/[tab]/page.tsx 中的 VALID_TABS 保持一致）
const VALID_TABS = [
  'account', 'preferences', 'personalization', 'agents', 'security',
  'riskRules', 'models', 'defaultModel', 'search', 'mcp', 'skills',
  'skillQuality', 'credentials', 'cron', 'checkpoint',
  'channels', 'voice', 'developer', 'importExport', 'companion',
  'usageStatistics', 'system', 'about',
];

// 支持的语言
const LANGUAGES = ['zh', 'en', 'ja', 'ko', 'de'];

/**
 * `agent.configPanel` 下必须在所有语言中存在的字符串键（与 `useTranslations('agent.configPanel')` 对齐）。
 * 各 locale 该对象的子键集合可与 en 不完全一致（如 ja 另有 jit 文案），但下列键不得缺失，以免运行时 MISSING_MESSAGE。
 */
const AGENT_CONFIG_PANEL_REQUIRED_STRING_KEYS = ['autoRestoreDomains', 'autoRestoreDomainsDesc'];

let hasErrors = false;

console.log('🔍 开始验证翻译完整性...\n');

// 读取所有语言文件
const translations = {};
for (const lang of LANGUAGES) {
  const filePath = resolve(rootDir, `locales/${lang}.json`);
  try {
    translations[lang] = JSON.parse(readFileSync(filePath, 'utf-8'));
    console.log(`✅ 已加载 ${lang}.json`);
  } catch (error) {
    console.error(`❌ 无法加载 ${lang}.json: ${error.message}`);
    hasErrors = true;
  }
}

console.log('\n');

// 验证1: metadata.settingsTabs 必须包含所有 VALID_TABS
console.log('📋 验证 metadata.settingsTabs 完整性...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const settingsTabs = data.metadata?.settingsTabs || {};
  const missingTabs = [];

  for (const tab of VALID_TABS) {
    const tabData = settingsTabs[tab];
    if (!tabData) {
      missingTabs.push(`${tab} (完全缺失)`);
    } else if (!tabData.title || !tabData.description) {
      const missing = [];
      if (!tabData.title) missing.push('title');
      if (!tabData.description) missing.push('description');
      missingTabs.push(`${tab} (缺少: ${missing.join(', ')})`);
    }
  }

  if (missingTabs.length > 0) {
    console.error(`  ❌ ${lang}.json 缺少以下tabs:`);
    missingTabs.forEach(tab => console.error(`     - ${tab}`));
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json metadata.settingsTabs 完整`);
  }
}

// 验证2: settings.menu 必须包含所有 VALID_TABS
console.log('\n📋 验证 settings.menu 完整性...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const settingsMenu = data.settings?.menu || {};
  const missingMenuItems = [];

  for (const tab of VALID_TABS) {
    if (!settingsMenu[tab]) {
      missingMenuItems.push(tab);
    }
  }

  if (missingMenuItems.length > 0) {
    console.error(`  ❌ ${lang}.json settings.menu 缺少: ${missingMenuItems.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json settings.menu 完整`);
  }
}

// 验证3: settings.developer 必须包含关键keys
console.log('\n📋 验证 settings.developer 关键keys...');
const requiredDeveloperKeys = ['showSystemMessages', 'showSystemMessagesDesc', 'title', 'description'];
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const developer = data.settings?.developer || {};
  const missingKeys = requiredDeveloperKeys.filter(key => !developer[key]);

  if (missingKeys.length > 0) {
    console.error(`  ❌ ${lang}.json settings.developer 缺少: ${missingKeys.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json settings.developer 完整`);
  }
}

// 验证4: 检查zh.json和en.json的key结构是否一致
console.log('\n📋 验证 zh.json 和 en.json 结构一致性...');
function getAllKeys(obj, prefix = '') {
  const keys = new Set();
  if (typeof obj !== 'object' || obj === null) {
    return keys;
  }
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    keys.add(fullKey);
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      getAllKeys(value, fullKey).forEach(k => keys.add(k));
    }
  }
  return keys;
}

const zhKeys = getAllKeys(translations.zh);
const enKeys = getAllKeys(translations.en);

const missingInEn = [...zhKeys].filter(k => !enKeys.has(k));
const missingInZh = [...enKeys].filter(k => !zhKeys.has(k));

if (missingInEn.length > 0) {
  console.warn(`  ⚠️  en.json 缺少 ${missingInEn.length} 个keys (zh.json中存在):`);
  missingInEn.slice(0, 10).forEach(key => console.warn(`     - ${key}`));
  if (missingInEn.length > 10) {
    console.warn(`     ... 还有 ${missingInEn.length - 10} 个`);
  }
  hasErrors = true;
}

if (missingInZh.length > 0) {
  console.warn(`  ⚠️  zh.json 缺少 ${missingInZh.length} 个keys (en.json中存在):`);
  missingInZh.slice(0, 10).forEach(key => console.warn(`     - ${key}`));
  if (missingInZh.length > 10) {
    console.warn(`     ... 还有 ${missingInZh.length - 10} 个`);
  }
  hasErrors = true;
}

if (missingInEn.length === 0 && missingInZh.length === 0) {
  console.log(`  ✅ zh.json 和 en.json 结构一致`);
}

// 验证5: agent.configPanel 关键 keys（全语言，与 AgentConfigEditDialog 的 useTranslations 命名空间一致）
console.log('\n📋 验证 agent.configPanel 关键 keys（全语言）...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const panel = data.agent?.configPanel;
  if (!panel || typeof panel !== 'object') {
    console.error(`  ❌ ${lang}.json 缺少或无效 agent.configPanel`);
    hasErrors = true;
    continue;
  }

  const missing = [];
  for (const key of AGENT_CONFIG_PANEL_REQUIRED_STRING_KEYS) {
    const v = panel[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(key);
    }
  }
  if (missing.length > 0) {
    console.error(
      `  ❌ ${lang}.json agent.configPanel 缺少或非空字符串: ${missing.join(', ')}`,
    );
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json agent.configPanel 关键 keys 完整`);
  }
}

// 最终结果
console.log('\n' + '='.repeat(50));
if (hasErrors) {
  console.error('❌ 验证失败！发现翻译完整性问题。');
  process.exit(1);
} else {
  console.log('✅ 验证通过！所有翻译文件完整且一致。');
  process.exit(0);
}
