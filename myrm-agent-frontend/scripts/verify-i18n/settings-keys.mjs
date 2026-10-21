/**
 * [INPUT] src/components/features/settings/settingsRoutes.ts (POS: 设置 Tab 路由 SSOT)
 *         context::LANGUAGES (POS: 共享上下文与支持语言)
 * [OUTPUT] readSettingsTabs / verifySettingsTabs / verifySettingsMenu / verifyDeveloperKeys
 * [POS] verify-i18n 的设置页文案完整性检查（验证 1/2/3）：每个路由 Tab 必须在全部语言有 metadata、菜单项与 developer 关键键。
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { LANGUAGES } from './context.mjs';

// 设置 Tab 清单直接读取路由 SSOT（settingsRoutes.ts）。
export function readSettingsTabs(rootDir) {
  const routesPath = resolve(rootDir, 'src/components/features/settings/settingsRoutes.ts');
  const source = readFileSync(routesPath, 'utf-8');
  const blockMatch = source.match(/SETTINGS_TABS\s*=\s*\[([\s\S]*?)\]\s*as\s*const/);
  if (!blockMatch) {
    throw new Error('Could not parse SETTINGS_TABS from settingsRoutes.ts');
  }
  return [...blockMatch[1].matchAll(/['"]([^'"]+)['"]/g)].map((match) => match[1]);
}

// 验证1: metadata.settingsTabs 必须包含所有 SETTINGS_TABS
export function verifySettingsTabs(ctx, settingsTabs) {
  console.log('📋 验证 metadata.settingsTabs 完整性...');
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const tabsData = data.metadata?.settingsTabs || {};
    const missingTabs = [];

    for (const tab of settingsTabs) {
      const tabData = tabsData[tab];
      if (!tabData) {
        missingTabs.push(`${tab} (完全缺失)`);
      } else if (!tabData.title || !tabData.description) {
        const missing = [];
        if (!tabData.title) {
          missing.push('title');
        }
        if (!tabData.description) {
          missing.push('description');
        }
        missingTabs.push(`${tab} (缺少: ${missing.join(', ')})`);
      }
    }

    if (missingTabs.length > 0) {
      console.error(`  ❌ ${lang}.json 缺少以下tabs:`);
      missingTabs.forEach((tab) => console.error(`     - ${tab}`));
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json metadata.settingsTabs 完整`);
    }
  }
}

// 验证2: settings.menu 必须包含所有 SETTINGS_TABS
export function verifySettingsMenu(ctx, settingsTabs) {
  console.log('\n📋 验证 settings.menu 完整性...');
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const settingsMenu = data.settings?.menu || {};
    const missingMenuItems = settingsTabs.filter((tab) => !settingsMenu[tab]);

    if (missingMenuItems.length > 0) {
      console.error(`  ❌ ${lang}.json settings.menu 缺少: ${missingMenuItems.join(', ')}`);
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json settings.menu 完整`);
    }
  }
}

const REQUIRED_DEVELOPER_KEYS = ['showSystemMessages', 'showSystemMessagesDesc', 'title', 'description'];

// 验证3: settings.developer 必须包含关键keys
export function verifyDeveloperKeys(ctx) {
  console.log('\n📋 验证 settings.developer 关键keys...');
  for (const lang of LANGUAGES) {
    const data = ctx.translations[lang];
    if (!data) {
      continue;
    }

    const developer = data.settings?.developer || {};
    const missingKeys = REQUIRED_DEVELOPER_KEYS.filter((key) => !developer[key]);

    if (missingKeys.length > 0) {
      console.error(`  ❌ ${lang}.json settings.developer 缺少: ${missingKeys.join(', ')}`);
      ctx.hasErrors = true;
    } else {
      console.log(`  ✅ ${lang}.json settings.developer 完整`);
    }
  }
}
