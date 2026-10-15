/**
 * [INPUT] context::LANGUAGES (POS: 共享上下文与支持语言)；ctx.translations (POS: 已加载的六语系 locale)
 * [OUTPUT] verifyAgentConfigPanel / verifyKanbanClosure / verifyArtifactsCenter / verifyCronBlueprint / verifyCronExecutionPolicy / verifyBuiltinToolTexts
 * [POS] verify-i18n 的业务命名空间关键键检查（验证 4/5/5b/6/7）：这些键由运行时 `useTranslations` 直接读取，任一语言缺失即 MISSING_MESSAGE。
 */

import { LANGUAGES } from './context.mjs';

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

const isNonEmptyString = (value) => typeof value === 'string' && value.length > 0;

/** `section` 中缺失或非空字符串的键（带可选前缀，保持传入顺序）。 */
function missingStringKeys(section, keys, prefix = '') {
  return keys.filter((key) => !isNonEmptyString(section[key])).map((key) => `${prefix}${key}`);
}

/** 命名空间对象必须存在且其全部必需键为非空字符串（验证 5/5b/6 同构）。 */
function verifyRequiredStringKeys(ctx, { heading, label, select, requiredKeys, okText }) {
  console.log(heading);
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const section = select(data);
    if (!section || typeof section !== 'object') {
      console.error(`  ❌ ${lang}.json 缺少或无效 ${label}`);
      ctx.hasErrors = true;
      continue;
    }

    const missing = missingStringKeys(section, requiredKeys);
    if (missing.length > 0) {
      console.error(`  ❌ ${lang}.json ${label} 缺少或非空字符串: ${missing.join(', ')}`);
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json ${okText}`);
    }
  }
}

// 验证5: agent.configPanel 关键 keys（全语言，与 AgentConfigEditDialog 的 useTranslations 命名空间一致）
export function verifyAgentConfigPanel(ctx) {
  verifyRequiredStringKeys(ctx, {
    heading: '\n📋 验证 agent.configPanel 关键 keys（全语言）...',
    label: 'agent.configPanel',
    select: (data) => data.agent?.configPanel,
    requiredKeys: AGENT_CONFIG_PANEL_REQUIRED_STRING_KEYS,
    okText: 'agent.configPanel 关键 keys 完整',
  });
}

// 验证5b: kanban Chat ↔ Board closure keys（全语言）
export function verifyKanbanClosure(ctx) {
  verifyRequiredStringKeys(ctx, {
    heading: '\n📋 验证 kanban Chat↔Board closure keys（全语言）...',
    label: 'kanban',
    select: (data) => data.kanban,
    requiredKeys: KANBAN_CHAT_CLOSURE_REQUIRED_STRING_KEYS,
    okText: 'kanban Chat↔Board closure keys 完整',
  });
}

// 验证6: artifacts 命名空间 — ArtifactsCenter 所需 keys（全语言）
export function verifyArtifactsCenter(ctx) {
  verifyRequiredStringKeys(ctx, {
    heading: '\n📋 验证 artifacts 命名空间 ArtifactsCenter keys（全语言）...',
    label: 'artifacts',
    select: (data) => data.artifacts,
    requiredKeys: ARTIFACTS_CENTER_REQUIRED_STRING_KEYS,
    okText: 'artifacts ArtifactsCenter keys 完整',
  });
}

// 验证4: cron.blueprint 扩展槽位标签（全语言，防 BlueprintInlineFill MISSING_MESSAGE）
export function verifyCronBlueprint(ctx) {
  console.log('\n📋 验证 cron.blueprint 槽位标签（全语言）...');
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const missing = missingStringKeys(data.cron?.blueprint ?? {}, CRON_BLUEPRINT_SLOT_KEYS);
    if (missing.length > 0) {
      console.error(`  ❌ ${lang}.json cron.blueprint 缺少: ${missing.join(', ')}`);
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json cron.blueprint 槽位标签完整`);
    }
  }
}

// 验证5: cron 执行策略编辑器（CapabilityEditor，全语言）
export function verifyCronExecutionPolicy(ctx) {
  console.log('\n📋 验证 cron 执行策略编辑器文案（全语言）...');
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const cron = data.cron ?? {};
    const missing = [
      ...missingStringKeys(cron, CRON_EXECUTION_POLICY_STRING_KEYS),
      ...missingStringKeys(cron.capPreset ?? {}, CRON_CAP_PRESET_KEYS, 'capPreset.'),
      ...missingStringKeys(cron.toolPreset ?? {}, CRON_TOOL_PRESET_KEYS, 'toolPreset.'),
    ];
    if (missing.length > 0) {
      console.error(`  ❌ ${lang}.json cron 执行策略缺少: ${missing.join(', ')}`);
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json cron 执行策略文案完整`);
    }
  }
}

// 验证7: agent.configPanel builtinToolNames / builtinToolDescs（全语言，与 BuiltinToolsPanel 对齐）
export function verifyBuiltinToolTexts(ctx) {
  console.log('\n📋 验证 agent.configPanel builtin 工具文案（全语言）...');
  const enPanel = ctx.translations.en?.agent?.configPanel;
  const enBuiltinNames = enPanel?.builtinToolNames;
  const enBuiltinDescs = enPanel?.builtinToolDescs;
  if (!enBuiltinNames || typeof enBuiltinNames !== 'object') {
    console.error('  ❌ en.json 缺少 agent.configPanel.builtinToolNames');
    ctx.hasErrors = true;
    return;
  }
  if (!enBuiltinDescs || typeof enBuiltinDescs !== 'object') {
    console.error('  ❌ en.json 缺少 agent.configPanel.builtinToolDescs');
    ctx.hasErrors = true;
    return;
  }

  const requiredBuiltinKeys = Object.keys(enBuiltinNames).sort();
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const panel = data.agent?.configPanel;
    const missingNames = missingStringKeys(panel?.builtinToolNames ?? {}, requiredBuiltinKeys);
    const missingDescs = missingStringKeys(panel?.builtinToolDescs ?? {}, requiredBuiltinKeys);

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
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json agent.configPanel builtin 工具文案完整`);
    }
  }
}
