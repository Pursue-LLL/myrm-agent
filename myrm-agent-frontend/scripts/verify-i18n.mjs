#!/usr/bin/env node
/**
 * 翻译完整性验证脚本（i18n 质量门禁）。
 *
 * - metadata.settingsTabs / settings.menu / settings.developer 完整性
 * - agent.configPanel / kanban / artifacts / cron 关键 string 键在全部 6 种语言均存在（防 MISSING_MESSAGE）
 * - SSR shell 组件不得 useTranslations(deferred namespace)（与 locale-manifest.ts 对齐）
 * - home-route settings i18n shell contract（scan-home-i18n-shell.mjs）
 * - 全语言 vs en：key parity（缺键=ERROR / 孤儿键=ERROR）、叶子类型一致、ICU 占位符变量一致、
 *   ICU 花括号平衡、翻译壳检测（含单 token 英文壳，豁免见 scripts/i18n-shell-allowlist.json）、
 *   双语对照脏值检测（"本地语 / English" 并存）、异常哨兵（[object Object] / 空串）
 * - en 纯净性门禁：en（SSOT）叶子值不得混入 CJK（语言名 allowlist 豁免），防 SSOT 污染连锁
 * - ko/de 非本语言文字纯净门禁：拉丁/谚文系语言（ko/de）文案中出现汉字或日文假名即残留
 *   （语言名/跨语言术语豁免），与 en 9f 对称
 * - zh-TW/ja 简体独有字形纯净门禁：繁体中文/日文文案中出现简体独有字形（相对繁体/日文新字体）
 *   即残留（语言名/跨语言术语豁免），与 en 9f / ko-de 9g 对称
 * - zh/ja/ko/zh-TW 句子级纯英文残留门禁：非拉丁系语言整条文案仍是英文句子即残留
 *   （值≠en 且纯 ASCII 且含 ≥2 纯字母英文单词且带句尾标点或英文功能词；字段名/品牌名/
 *   单技术词天然豁免），与 9g/9h/9j「混入字形」检测互补拦截「整条还是英文」
 *
 * 支持语言必须与 src/i18n/config.ts locales 一致：zh / en / ja / ko / de / zh-TW。
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { execSync } from 'node:child_process';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';
import {
  collectTranslationShells,
  isLegitSameValue,
  loadShellAllowlist,
  resolvePath,
  walkTypes,
} from './i18n-shell-core.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, '..');

// 有效的tabs列表（必须与 app/settings/[tab]/page.tsx 中的 VALID_TABS 保持一致）
const VALID_TABS = [
  'account', 'preferences', 'theme-studio', 'personalization', 'agents', 'security',
  'riskRules', 'models', 'defaultModel', 'search', 'mcp', 'skills',
  'skillQuality', 'toolStability', 'toolQuality', 'evolutionPending', 'evolutionRejection', 'eval',
  'credentials', 'wiki', 'memory', 'cron', 'kanban', 'checkpoint',
  'channels', 'channelRouting', 'voice', 'openaiApi', 'integrationCatalog', 'integrationMemory',
  'extensionBridge', 'connect', 'hosting', 'workspaceRules', 'developer', 'importExport',
  'companion', 'usageStatistics', 'experimentalFeatures', 'memory-backup', 'memory-cloud-backup',
  'memory-migration', 'enterprise', 'system', 'about',
];

// 支持的语言（必须与 src/i18n/config.ts locales 一致）
const LANGUAGES = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'];

/**
 * `agent.configPanel` 下必须在所有语言中存在的字符串键（与 `useTranslations('agent.configPanel')` 对齐）。
 * 各 locale 该对象的子键集合可与 en 不完全一致（如 ja 另有 jit 文案），但下列键不得缺失，以免运行时 MISSING_MESSAGE。
 */
const AGENT_CONFIG_PANEL_REQUIRED_STRING_KEYS = [
  'autoRestoreDomains',
  'autoRestoreDomainsDesc',
  'kanbanBoardHint',
  'kanbanBoardLoading',
  'kanbanNoBoardsHint',
  'kanbanOpenSettings',
  'kanbanTargetBoard',
  'kanbanSelectBoardPlaceholder',
  'kanbanActiveBoard',
];

/** `useTranslations('kanban')` keys for Chat ↔ Board closure UI (card, filter chip, drawer). */
const KANBAN_CHAT_CLOSURE_REQUIRED_STRING_KEYS = [
  'executionTrace',
  'openSourceChat',
  'viewBoardTasksFromChat',
  'sourceChatFilterActive',
  'chatTaskCreatedTitle',
  'chatTaskCreatedSuccess',
  'chatTaskCreatedOpenBoard',
  'clearSourceChatFilter',
];

/** `useTranslations('artifacts')` keys used by ArtifactsCenter — must exist in all locales. */
const ARTIFACTS_CENTER_REQUIRED_STRING_KEYS = [
  'title',
  'empty',
  'select_prompt',
  'no_desc',
  'version_history',
  'tamper_free',
  'corrupted',
  'verifying',
  'verify_hash',
  'loading_versions',
  'auto_saved_version',
  'preview',
  'download',
];

/** Extended blueprint slot labels used by `BlueprintInlineFill` (`t(slot.label)`). */
const CRON_BLUEPRINT_SLOT_KEYS = [
  'slotTime',
  'slotDay',
  'slotWeekdays',
  'slotMessage',
  'slotTopic',
  'slotCompetitors',
  'slotHabits',
  'slotBrand',
  'slotPlatforms',
  'slotKeywords',
  'slotOptional',
  'slotSubject',
];

/** CapabilityEditor execution policy strings (`useTranslations('cron')`). */
const CRON_EXECUTION_POLICY_STRING_KEYS = [
  'toolsAllowedLabel',
  'toolsAllowedDesc',
  'toolsAllowedAllHint',
  'executionPolicyUpdated',
];

const CRON_CAP_PRESET_KEYS = ['research', 'devops', 'full'];
const CRON_TOOL_PRESET_KEYS = ['webOnly', 'research', 'full'];

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

function readDeferredNamespaces() {
  const manifestPath = resolve(rootDir, 'src/i18n/locale-manifest.ts');
  const source = readFileSync(manifestPath, 'utf-8');
  const blockMatch = source.match(/DEFERRED_NAMESPACES\s*=\s*\[([\s\S]*?)\]\s*as\s*const/);
  if (!blockMatch) {
    throw new Error('Could not parse DEFERRED_NAMESPACES from locale-manifest.ts');
  }
  return [...blockMatch[1].matchAll(/['"]([^'"]+)['"]/g)].map((match) => match[1]);
}

function verifyShellDeferredNamespaceGate() {
  console.log('📋 验证 SSR shell 组件未引用 deferred i18n namespace...');
  const deferredNamespaces = new Set(readDeferredNamespaces());
  const shellFiles = [];

  for (const relativePath of SSR_SHELL_I18N_SCAN_ROOTS) {
    const absolutePath = resolve(rootDir, relativePath);
    const stat = statSync(absolutePath);
    if (stat.isDirectory()) {
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
        hasErrors = true;
      }
    }
  }

  if (shellErrors === 0) {
    console.log(
      `  ✅ SSR shell 扫描通过（${shellFiles.length} 个文件，deferred: ${[...deferredNamespaces].join(', ') || '(none)'}）`,
    );
  }
}

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

verifyShellDeferredNamespaceGate();

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

// 验证5b: kanban Chat ↔ Board closure keys（全语言）
console.log('\n📋 验证 kanban Chat↔Board closure keys（全语言）...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const kanban = data.kanban;
  if (!kanban || typeof kanban !== 'object') {
    console.error(`  ❌ ${lang}.json 缺少或无效 kanban`);
    hasErrors = true;
    continue;
  }

  const missing = [];
  for (const key of KANBAN_CHAT_CLOSURE_REQUIRED_STRING_KEYS) {
    const v = kanban[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(key);
    }
  }
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json kanban 缺少或非空字符串: ${missing.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json kanban Chat↔Board closure keys 完整`);
  }
}

// 验证6: artifacts 命名空间 — ArtifactsCenter 所需 keys（全语言）
console.log('\n📋 验证 artifacts 命名空间 ArtifactsCenter keys（全语言）...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const artifacts = data.artifacts;
  if (!artifacts || typeof artifacts !== 'object') {
    console.error(`  ❌ ${lang}.json 缺少或无效 artifacts`);
    hasErrors = true;
    continue;
  }

  const missing = [];
  for (const key of ARTIFACTS_CENTER_REQUIRED_STRING_KEYS) {
    const v = artifacts[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(key);
    }
  }
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json artifacts 缺少或非空字符串: ${missing.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json artifacts ArtifactsCenter keys 完整`);
  }
}

// 验证4: cron.blueprint 扩展槽位标签（全语言，防 BlueprintInlineFill MISSING_MESSAGE）
console.log('\n📋 验证 cron.blueprint 槽位标签（全语言）...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const blueprint = data.cron?.blueprint ?? {};
  const missing = [];
  for (const key of CRON_BLUEPRINT_SLOT_KEYS) {
    const v = blueprint[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(key);
    }
  }
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json cron.blueprint 缺少: ${missing.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json cron.blueprint 槽位标签完整`);
  }
}

// 验证5: cron 执行策略编辑器（CapabilityEditor，全语言）
console.log('\n📋 验证 cron 执行策略编辑器文案（全语言）...');
for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data) continue;

  const cron = data.cron ?? {};
  const missing = [];
  for (const key of CRON_EXECUTION_POLICY_STRING_KEYS) {
    const v = cron[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(key);
    }
  }
  const capPreset = cron.capPreset ?? {};
  for (const key of CRON_CAP_PRESET_KEYS) {
    const v = capPreset[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(`capPreset.${key}`);
    }
  }
  const toolPreset = cron.toolPreset ?? {};
  for (const key of CRON_TOOL_PRESET_KEYS) {
    const v = toolPreset[key];
    if (typeof v !== 'string' || v.length === 0) {
      missing.push(`toolPreset.${key}`);
    }
  }
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json cron 执行策略缺少: ${missing.join(', ')}`);
    hasErrors = true;
  } else {
    console.log(`  ✅ ${lang}.json cron 执行策略文案完整`);
  }
}

// 验证7: agent.configPanel builtinToolNames / builtinToolDescs（全语言，与 BuiltinToolsPanel 对齐）
console.log('\n📋 验证 agent.configPanel builtin 工具文案（全语言）...');
const enPanel = translations.en?.agent?.configPanel;
const enBuiltinNames = enPanel?.builtinToolNames;
const enBuiltinDescs = enPanel?.builtinToolDescs;
if (!enBuiltinNames || typeof enBuiltinNames !== 'object') {
  console.error('  ❌ en.json 缺少 agent.configPanel.builtinToolNames');
  hasErrors = true;
} else if (!enBuiltinDescs || typeof enBuiltinDescs !== 'object') {
  console.error('  ❌ en.json 缺少 agent.configPanel.builtinToolDescs');
  hasErrors = true;
} else {
  const requiredBuiltinKeys = Object.keys(enBuiltinNames).sort();
  for (const lang of LANGUAGES) {
    const data = translations[lang];
    if (!data) continue;

    const panel = data.agent?.configPanel;
    const names = panel?.builtinToolNames;
    const descs = panel?.builtinToolDescs;
    const missingNames = [];
    const missingDescs = [];

    for (const key of requiredBuiltinKeys) {
      const nameVal = names?.[key];
      if (typeof nameVal !== 'string' || nameVal.length === 0) {
        missingNames.push(key);
      }
      const descVal = descs?.[key];
      if (typeof descVal !== 'string' || descVal.length === 0) {
        missingDescs.push(key);
      }
    }

    if (missingNames.length > 0 || missingDescs.length > 0) {
      if (missingNames.length > 0) {
        console.error(
          `  ❌ ${lang}.json agent.configPanel.builtinToolNames 缺少或非空字符串: ${missingNames.join(', ')}`,
        );
      }
      if (missingDescs.length > 0) {
        console.error(
          `  ❌ ${lang}.json agent.configPanel.builtinToolDescs 缺少或非空字符串: ${missingDescs.join(', ')}`,
        );
      }
      hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json agent.configPanel builtin 工具文案完整`);
    }
  }
}

// 验证8: home-route settings i18n shell contract（防 chat 首屏 MISSING_MESSAGE）
console.log('\n📋 验证 home-route settings i18n shell contract...');
try {
  execSync('node scripts/scan-home-i18n-shell.mjs', { stdio: 'inherit', cwd: rootDir });
  console.log('  ✅ home-route settings shell contract 通过');
} catch {
  hasErrors = true;
}

// 验证9: 全量 key parity + 类型一致 + 占位符 + 壳检测 + 哨兵（所有语言 vs en）
console.log('\n📋 验证全量 key parity / 类型 / 占位符 / 翻译壳 / 异常哨兵...');

// 壳检测 allowlist（scripts/i18n-shell-allowlist.json）
let shellAllowlists = { allowedSameValues: new Set(), allowedSameKeys: new Set() };
let ALLOWED_SAME_KEYS = new Set();
let ALLOWED_MIXED_VALUES = new Set();
let ALLOWED_MIXED_KEYS = new Set();
/** @type {Record<string, Array<string | RegExp | null>>} */
let glossaryForbiddenByLocale = {};
try {
  shellAllowlists = loadShellAllowlist(rootDir);
  ALLOWED_SAME_KEYS = shellAllowlists.allowedSameKeys;
  const allowlist = JSON.parse(
    readFileSync(resolve(rootDir, 'scripts/i18n-shell-allowlist.json'), 'utf-8'),
  );
  ALLOWED_MIXED_VALUES = new Set(allowlist.allowedMixedValues || []);
  ALLOWED_MIXED_KEYS = new Set(allowlist.allowedMixedKeys || []);
  const glossary = JSON.parse(
    readFileSync(resolve(rootDir, 'scripts/i18n-glossary.json'), 'utf-8'),
  );
  for (const [locale, config] of Object.entries(glossary.locales || {})) {
    // 预编译：字符串模式转小写供 lower.includes 匹配；/正则/ 模式编译为 RegExp 复用
    //（避免 checkValue 内每 key 重复 new RegExp，约 22 万次编译；非法正则在此 fail-fast）
    glossaryForbiddenByLocale[locale] = (config.forbidden || []).map((p) => {
      const s = String(p);
      if (s.startsWith('/') && s.endsWith('/') && s.length > 2) {
        try {
          return new RegExp(s.slice(1, -1), 'i');
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          console.error(`  ❌ ${locale}.json glossary 非法正则 ${JSON.stringify(s)}: ${message}`);
          hasErrors = true;
          return null;
        }
      }
      return s.toLowerCase();
    });
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`  ❌ 无法加载 i18n allowlist/glossary: ${message}`);
  hasErrors = true;
}

function placeholderSet(value) {
  const matches = String(value).match(/\{([a-zA-Z_][\w.-]*)(?:,|})/g) || [];
  return matches
    .map((match) => match.replace(/^\{/, '').replace(/[,}]$/, ''))
    .sort()
    .join('|');
}

/** ICU 花括号是否成对平衡（防 next-intl 运行时解析崩溃）。 */
function isBraceBalanced(value) {
  let depth = 0;
  for (const ch of value) {
    if (ch === '{') depth += 1;
    else if (ch === '}') depth -= 1;
    if (depth < 0) return false;
  }
  return depth === 0;
}

/**
 * 非拉丁文字区间（汉字 \u4e00-\u9fff、日文假名 \u3040-\u30ff、韩文谚文 \uac00-\ud7af、
 * 全角标点 \u3000-\u303f / \uff00-\uffef），用于 en 纯净性与双语对照检测。
 * 覆盖全部 6 语言（zh / en / ja / ko / de / zh-TW），杜绝假名/谚文双语脏值漏检。
 */
const NON_LATIN_RE = /[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]/;

/**
 * 拉丁/谚文系语言（ko/de）纯净性门禁的非本语言文字范围：汉字（U+3400–U+9FFF，
 * 含扩展A区）+ 日文假名（U+3040–U+30FF）。ko（谚文）与 de（拉丁）文案中出现即代表残留。
 * 不含谚文（ko 合法字符）与全角符号；汉字范围与 en 9f NON_LATIN_RE 对齐。
 */
const FOREIGN_SCRIPT_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]/;

/**
 * de（拉丁系）专用的非本语言文字范围：在 FOREIGN_SCRIPT_RE 基础上追加谚文
 * （U+AC00–U+D7AF）。de 中出现谚文是残留；ko 的谚文是合法字符，故 ko 仅用
 * FOREIGN_SCRIPT_RE。
 */
const FOREIGN_SCRIPT_DE_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]/;

/**
 * 双语对照脏值：同一语义被写成"本地语 / English"（如 "はい / Yes"、"上下文健康 / Context Health"）。
 * 判定：恰好两段，一段纯 ASCII（英文），另一段含非拉丁文字（本地语），且不含 ICU 占位符对照。
 * 排除合理情形：占位符对照（{shown} / {total}）、术语对照（MCP / 技能设置）、路径/URL。
 */
function isBilingualDirty(value) {
  if (typeof value !== 'string' || value.length > 160) return false;
  if (!NON_LATIN_RE.test(value) || !/[a-zA-Z]/.test(value)) return false;
  if (!value.includes(' / ') || /\{/.test(value)) return false;
  const parts = value.split(' / ');
  if (parts.length !== 2) return false;
  const [a, b] = parts.map((s) => s.trim());
  if (!a || !b) return false;
  const asciiOnly = (s) => s.length > 0 && [...s].every((c) => c.charCodeAt(0) <= 0x7f);
  const nonLatinOnly = (s) => !/[a-zA-Z]/.test(s) && NON_LATIN_RE.test(s);
  return (asciiOnly(a) && nonLatinOnly(b)) || (nonLatinOnly(a) && asciiOnly(b));
}

function reportShells(locale, shells) {
  if (shells.length === 0) return;
  console.error(`  ❌ ${locale}.json 存在 ${shells.length} 个翻译壳（值与英文一致）：`);
  shells.slice(0, 15).forEach(({ path, value }) => {
    console.error(`     - ${path} = ${JSON.stringify(value.slice(0, 80))}`);
  });
  if (shells.length > 15) console.error(`     ... 还有 ${shells.length - 15} 个`);
  hasErrors = true;
}

/**
 * 值是否含指定残留字形：字符串直接检测，数组逐元素检测字符串成员。
 * 与 9d checkArray 对齐，覆盖数组叶子（i18n 选项列表）的纯净性，
 * 避免 9f/9g/9h 对数组 leaf 漏检。
 */
function containsResidue(value, residueRe) {
  if (typeof value === 'string') return residueRe.test(value);
  if (Array.isArray(value)) {
    return value.some((item) => typeof item === 'string' && residueRe.test(item));
  }
  return false;
}

/**
 * 9k 句子级纯英文残留判定（zh/ja/ko/zh-TW）：
 * 非拉丁系语言的整条文案若仍是英文句子（含 ≥2 个纯字母英文单词且带句尾标点
 * 或英文功能词），即未本地化残留。与 9g/9h/9j 的「混入字形」检测互补——它们
 * 拦「本语言文案混入英文」，本检测拦「整条还是英文」。
 *
 * 判定为「句子级」而非「任意英文」：
 * - ≥2 个纯字母单词：排除单技术词（Agent/Token/Cookie）。
 * - 句尾标点 `! . ?` 或功能词命中：排除字段名/品牌名（App ID/Bot Token/
 *   Alibaba Cloud/Client Secret），这些是行业惯例保留英文的凭据名，翻译反而
 *   降低可识别性（用户从文档/API 得知的是英文术语）。
 */
const PURE_EN_SENTENCE_WORDS_RE = /[A-Za-z]{2,}/g;
const PURE_EN_SENTENCE_TAIL_RE = /[!?.]$/;
const PURE_EN_FUNCTION_WORDS = new Set([
  // UI 动作/状态词
  'login', 'logged', 'sign', 'successful', 'success', 'failed', 'fail', 'error', 'please',
  'click', 'expires', 'expired', 'waiting', 'wait', 'authorize', 'authorization', 'authorized',
  'connecting', 'connected', 'connect', 'generating', 'generate', 'select', 'scan', 'start',
  'prepare', 'preparing', 'validate', 'validating', 'cancel', 'cancelled', 'canceled', 'timeout',
  'retry', 'unknown', 'initializing', 'loading', 'saving', 'save', 'open', 'close', 'done',
  'completed', 'complete', 'processing', 'process', 'running', 'run', 'resumed', 'resume',
  'enabled', 'disabled', 'available', 'unavailable', 'missing', 'required', 'optional',
  'create', 'created', 'update', 'updated', 'remove', 'removed', 'add', 'added', 'search',
  'refresh', 'send', 'sent', 'receive', 'received', 'import', 'export', 'download', 'upload',
  'install', 'uninstall', 'enable', 'disable', 'verify', 'verification', 'check', 'testing',
  'test', 'connection', 'disconnect', 'disconnected', 'reconnect', 'pending', 'approved',
  'rejected', 'deleted', 'archived', 'restored', 'upgrade', 'subscribe', 'purchase',
  'confirm', 'delete', 'back', 'next', 'reset', 'restore', 'backup', 'migrate', 'migration',
  'share', 'shared', 'sync', 'paused', 'pause', 'blocked', 'unblocked', 'approve',
  // 英文虚词（句子结构标记）
  'the', 'a', 'an', 'of', 'at', 'for', 'with', 'and', 'or', 'to', 'from', 'by', 'in', 'on',
  'your', 'you', 'is', 'are', 'was', 'were', 'has', 'have', 'will', 'would', 'can', 'could',
  'should', 'must', 'not', 'no', 'yes', 'this', 'that', 'these', 'those', 'there', 'here',
  'more', 'less', 'all', 'any', 'some', 'none', 'only', 'just', 'also', 'then', 'than',
  'into', 'onto', 'over', 'under', 'about', 'after', 'before', 'during', 'between',
]);
function isEnglishSentenceResidue(value) {
  const words = value.toLowerCase().match(PURE_EN_SENTENCE_WORDS_RE) ?? [];
  if (words.length < 2) return false;
  if (PURE_EN_SENTENCE_TAIL_RE.test(value.trim())) return true;
  return words.some((word) => PURE_EN_FUNCTION_WORDS.has(word));
}

const enTypes = new Map();
walkTypes(translations.en, '', enTypes);
const enLeaves = [...enTypes.keys()];

// 9e. en.json 自身 ICU 花括号平衡（SSOT 损坏会连锁所有语言）
const enBraceErrors = [];
for (const key of enLeaves) {
  const enValue = resolvePath(translations.en, key);
  if (typeof enValue === 'string' && !isBraceBalanced(enValue)) {
    enBraceErrors.push(key);
  }
}
if (enBraceErrors.length > 0) {
  console.error(`  ❌ en.json 存在 ${enBraceErrors.length} 个 ICU 花括号不平衡键：`);
  enBraceErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
  hasErrors = true;
}

// 9f. en.json 纯净性（SSOT 语言纯净门禁）：en 叶子值不得混入非拉丁文字（语言名/品牌 allowlist 豁免）
const EN_PURITY_ALLOWED_KEYS = new Set([
  'settings.languageOptions.chinese',
  'settings.languageOptions.chineseTraditional',
  'settings.languageOptions.japanese',
  'settings.languageOptions.korean',
  'settings.languageOptions.german',
]);

/**
 * ko/de 非本语言文字纯净门禁豁免键：在 en 9f 语言名豁免基础上，追加跨语言术语
 * agent.formalKoreanReplies.title/description（de 中写成「합니다体」/「합니다체」，
 * 「体」为日语汉字、「체」为谚文，描述韩语敬语体 .합니다 时有意保留，非残留）。
 */
const FOREIGN_SCRIPT_ALLOWED_KEYS = new Set([
  ...EN_PURITY_ALLOWED_KEYS,
  'agent.formalKoreanReplies.title',
  'agent.formalKoreanReplies.description',
]);

/**
 * 加载简体独有字形集合文件并编译为检测正则。
 * 集合来源：scripts/zh-simplified-glyphs.txt（zh-TW，opencc cn→tw 从 zh 语料生成）、
 * scripts/ja-simplified-glyphs.txt（ja，opencc cn→jp 生成）。
 * 文件缺失/损坏时置 hasErrors 并返回 null（门禁 fail-safe）。
 */
function loadGlyphSet(relativePath, label) {
  try {
    const glyphs = readFileSync(resolve(rootDir, relativePath), 'utf-8').trim();
    return new RegExp(`[${glyphs}]`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`  ❌ 无法加载 ${relativePath}（${label}）: ${message}`);
    hasErrors = true;
    return null;
  }
}

/**
 * zh-TW 简体独有字形纯净门禁：繁体中文文案中出现简体独有字形即残留。
 * 集合由 generate-simplified-glyphs.mjs 从 zh.json 语料 + opencc cn→tw 生成，
 * 覆盖项目文案的简繁异形字；台湾合法两体字已豁免，简繁同形字自动排除。
 * 与 en 9f / ko-de 9g 纯净门禁对称。
 */
const SIMPLIFIED_GLYPH_RE = loadGlyphSet('scripts/zh-simplified-glyphs.txt', '简体字形集合');

/**
 * ja 简体独有字形纯净门禁：日文文案中出现简体独有字形（相对日文新字体）即残留。
 * 集合由 generate-simplified-glyphs.mjs 从 zh.json 语料 + opencc cn→jp 生成；
 * 日文合法同形/新字体字如 体/与/云/当/万 已豁免。
 * 与 zh-TW 9h / en 9f / ko-de 9g 纯净门禁对称。
 */
const JA_SIMPLIFIED_GLYPH_RE = loadGlyphSet('scripts/ja-simplified-glyphs.txt', 'ja 简体字形集合');

/**
 * zh-TW/ja 简体字形门禁豁免键：语言名（同 en 9f）+ 跨语言术语 합니다体（de/ko 9g 同源豁免）。
 */
const SIMPLIFIED_GLYPH_ALLOWED_KEYS = new Set([
  ...EN_PURITY_ALLOWED_KEYS,
  'agent.formalKoreanReplies.title',
  'agent.formalKoreanReplies.description',
]);
const enNonLatinErrors = [];
for (const key of enLeaves) {
  if (EN_PURITY_ALLOWED_KEYS.has(key)) continue;
  if (ALLOWED_SAME_KEYS.has(key) || ALLOWED_MIXED_KEYS.has(key)) continue;
  const enValue = resolvePath(translations.en, key);
  if (containsResidue(enValue, NON_LATIN_RE)) {
    enNonLatinErrors.push(key);
  }
}
if (enNonLatinErrors.length > 0) {
  console.error(`  ❌ en.json 存在 ${enNonLatinErrors.length} 个混入非拉丁文字的键（SSOT 污染，须修复为纯英文）：`);
  enNonLatinErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
  hasErrors = true;
}

for (const lang of LANGUAGES) {
  const data = translations[lang];
  if (!data || lang === 'en') continue;

  const localeTypes = new Map();
  walkTypes(data, '', localeTypes);

  // 9a. key parity
  const missing = enLeaves.filter((key) => !localeTypes.has(key));
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json 缺少 ${missing.length} 个 en 键：`);
    missing.slice(0, 15).forEach((key) => console.error(`     - ${key}`));
    if (missing.length > 15) console.error(`     ... 还有 ${missing.length - 15} 个`);
    hasErrors = true;
  }

// 9b. extra keys（en 中不存在的孤儿键 → ERROR，须清理）
const extras = [...localeTypes.keys()].filter((key) => !enTypes.has(key));
const realExtras = extras.filter((key) => !ALLOWED_SAME_KEYS.has(key));
  if (realExtras.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${realExtras.length} 个 en 中没有的键（孤儿键，须清理）：`);
    realExtras.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }

  // 9c. 类型一致
  const typeMismatches = [];
  for (const [key, enType] of enTypes) {
    if (!localeTypes.has(key)) continue;
    const localeType = localeTypes.get(key);
    if (localeType !== enType) typeMismatches.push(`${key} (en:${enType} vs ${lang}:${localeType})`);
  }
  if (typeMismatches.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${typeMismatches.length} 个类型不一致键：`);
    typeMismatches.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }

  // 9d. 占位符一致 + glossary forbidden + 双语对照 + 哨兵 + ICU 花括号（壳检测见 collectTranslationShells）
  const placeholderErrors = [];
  const glossaryErrors = [];
  const bilingualErrors = [];
  const sentinelErrors = [];
  const braceErrors = [];
  let foreignScriptErrors = [];
  let simplifiedGlyphErrors = [];
  let pureEnErrors = [];
  const forbiddenPatterns = glossaryForbiddenByLocale[lang] || [];

  const checkValue = (key, enValue, localeValue) => {
    if (typeof enValue !== 'string') return;
    if (typeof localeValue !== 'string') return;
    if (localeValue.includes('[object Object]')) {
      sentinelErrors.push(`${key} = "[object Object]"`);
      return;
    }
    if (!localeValue.trim()) {
      sentinelErrors.push(`${key} = 空字符串`);
      return;
    }
    if (!isBraceBalanced(localeValue)) {
      braceErrors.push(`${key} = ICU 花括号不平衡`);
      return;
    }
    if (placeholderSet(enValue) !== placeholderSet(localeValue)) {
      placeholderErrors.push(
        `${key}: en[${placeholderSet(enValue) || '(none)'}] vs ${lang}[${placeholderSet(localeValue) || '(none)'}]`,
      );
      return;
    }
    if (forbiddenPatterns.length > 0) {
      const lower = localeValue.toLowerCase();
      for (const pattern of forbiddenPatterns) {
        // 预编译模式：/正则/ → RegExp 实例（加载时已编译，非法正则在彼时 fail-fast 置 null）；
        // 普通模式 → 小写字符串（lower.includes 匹配）
        if (pattern === null) continue; // 非法正则已在加载阶段报错，此处跳过避免 null 参与匹配
        if (pattern instanceof RegExp) {
          if (pattern.test(localeValue)) {
            glossaryErrors.push(`${key} = forbidden pattern /${pattern.source}/`);
            break;
          }
        } else if (lower.includes(pattern)) {
          glossaryErrors.push(`${key} = forbidden pattern ${JSON.stringify(pattern)}`);
          break;
        }
      }
    }
    if (isBilingualDirty(localeValue) && !enValue.includes(' / ')) {
      if (!ALLOWED_MIXED_VALUES.has(localeValue) && !ALLOWED_MIXED_KEYS.has(key)) {
        bilingualErrors.push(`${key} = ${JSON.stringify(localeValue.slice(0, 80))}`);
      }
    }
  };

  const checkArray = (key, enArr, localeArr) => {
    enArr.forEach((item, index) => {
      const localeItem = Array.isArray(localeArr) ? localeArr[index] : undefined;
      if (typeof item === 'string' && typeof localeItem === 'string') {
        checkValue(`${key}[${index}]`, item, localeItem);
      }
    });
  };

  for (const key of enLeaves) {
    const enValue = resolvePath(translations.en, key);
    const localeValue = resolvePath(data, key);
    if (enValue === undefined || localeValue === undefined) continue;
    if (Array.isArray(enValue)) {
      checkArray(key, enValue, localeValue);
    } else {
      checkValue(key, enValue, localeValue);
    }
  }

  const shellErrors = collectTranslationShells(translations.en, data, shellAllowlists).map(
    ({ key, en }) => ({ path: key, value: en }),
  );
  reportShells(lang, shellErrors);
  if (glossaryErrors.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${glossaryErrors.length} 个 glossary forbidden 违规：`);
    glossaryErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }
  if (placeholderErrors.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${placeholderErrors.length} 个占位符不匹配：`);
    placeholderErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }
  if (bilingualErrors.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${bilingualErrors.length} 个双语对照脏值（本地语 / English 并存）：`);
    bilingualErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }
  if (sentinelErrors.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${sentinelErrors.length} 个异常哨兵：`);
    sentinelErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }
  if (braceErrors.length > 0) {
    console.error(`  ❌ ${lang}.json 存在 ${braceErrors.length} 个 ICU 花括号不平衡：`);
    braceErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
    hasErrors = true;
  }

  // 9g. 拉丁/谚文系语言（ko/de）非本语言文字纯净门禁：文案中出现汉字或日文假名即残留
  //（豁免见 FOREIGN_SCRIPT_ALLOWED_KEYS）；de 额外拦截谚文（FOREIGN_SCRIPT_DE_RE）。
  // 与 en 9f SSOT 纯净门禁对称。
  if (lang === 'ko' || lang === 'de') {
    const foreignScriptRe = lang === 'de' ? FOREIGN_SCRIPT_DE_RE : FOREIGN_SCRIPT_RE;
    for (const key of enLeaves) {
      if (FOREIGN_SCRIPT_ALLOWED_KEYS.has(key)) continue;
      const localeValue = resolvePath(data, key);
      if (containsResidue(localeValue, foreignScriptRe)) {
        foreignScriptErrors.push(key);
      }
    }
    if (foreignScriptErrors.length > 0) {
      console.error(`  ❌ ${lang}.json 存在 ${foreignScriptErrors.length} 个含非本语言文字的键：`);
      foreignScriptErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
      hasErrors = true;
    }
  }

  // 9h/9j. 简体独有字形纯净门禁：zh-TW 相对繁体字形、ja 相对日文新字体字形，出现即残留
  //（豁免见 SIMPLIFIED_GLYPH_ALLOWED_KEYS）。与 en 9f / ko-de 9g 纯净门禁对称。
  const simplifiedGlyphGates = [
    { lang: 'zh-TW', re: SIMPLIFIED_GLYPH_RE, label: '简体独有字形（须转繁体）' },
    { lang: 'ja', re: JA_SIMPLIFIED_GLYPH_RE, label: '简体独有字形（须转日文标准字形）' },
  ];
  for (const gate of simplifiedGlyphGates) {
    if (lang !== gate.lang || !gate.re) continue;
    const gateErrors = [];
    for (const key of enLeaves) {
      if (SIMPLIFIED_GLYPH_ALLOWED_KEYS.has(key)) continue;
      const localeValue = resolvePath(data, key);
      if (containsResidue(localeValue, gate.re)) {
        gateErrors.push(key);
      }
    }
    if (gateErrors.length > 0) {
      console.error(`  ❌ ${lang}.json 存在 ${gateErrors.length} 个含${gate.label}的键：`);
      gateErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
      hasErrors = true;
    }
    simplifiedGlyphErrors.push(...gateErrors);
  }

  // 9k. 非拉丁系语言（zh/ja/ko/zh-TW）句子级纯英文残留门禁：
  // 整条文案仍是英文句子（值≠en 且纯 ASCII 且含英文实义句子）即残留。
  // 与 9g/9h/9j 的「混入字形」检测互补（后者拦混入、本检测拦整条）；
  // 字段名/品牌名/单技术词天然豁免。de 为拉丁语系，纯英文残留无法以字符级
  // 与合法德文区分，不适用（由 9g 汉字/假名拦截 + glossary 语义词兜底）。
  // 数组叶子逐元素判定（与 9d checkArray / 9g-9j containsResidue 对称）。
  if (lang === 'zh' || lang === 'ja' || lang === 'ko' || lang === 'zh-TW') {
    const checkLeaf = (key, enLeaf, localeLeaf) => {
      if (typeof enLeaf !== 'string' || typeof localeLeaf !== 'string') return;
      if (localeLeaf === enLeaf) return; // 与 en 同值走壳检测（collectTranslationShells）
      if (localeLeaf === '' || /[\u0080-\uFFFF]/.test(localeLeaf)) return; // 空串/已含本语言字符
      if (isLegitSameValue(localeLeaf)) return; // 技术格式/占位模板/URL 等合法保留
      if (shellAllowlists.allowedSameValues.has(localeLeaf)) return;
      if (isEnglishSentenceResidue(localeLeaf)) pureEnErrors.push(key);
    };
    for (const key of enLeaves) {
      if (shellAllowlists.allowedSameKeys.has(key)) continue;
      const enValue = resolvePath(translations.en, key);
      const localeValue = resolvePath(data, key);
      if (Array.isArray(enValue)) {
        if (!Array.isArray(localeValue)) continue;
        enValue.forEach((item, index) => {
          checkLeaf(`${key}[${index}]`, item, localeValue[index]);
        });
      } else {
        checkLeaf(key, enValue, localeValue);
      }
    }
    if (pureEnErrors.length > 0) {
      console.error(`  ❌ ${lang}.json 存在 ${pureEnErrors.length} 个句子级纯英文残留键：`);
      pureEnErrors.slice(0, 10).forEach((key) => console.error(`     - ${key}`));
      hasErrors = true;
    }
  }

  if (missing.length === 0 && typeMismatches.length === 0 && shellErrors.length === 0
    && placeholderErrors.length === 0 && glossaryErrors.length === 0 && bilingualErrors.length === 0
    && sentinelErrors.length === 0 && braceErrors.length === 0 && foreignScriptErrors.length === 0
    && simplifiedGlyphErrors.length === 0 && pureEnErrors.length === 0) {
    console.log(`  ✅ ${lang}.json 全量 parity / 占位符 / 壳 / glossary / 双语对照 / 纯净门禁 检测 通过`);
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
