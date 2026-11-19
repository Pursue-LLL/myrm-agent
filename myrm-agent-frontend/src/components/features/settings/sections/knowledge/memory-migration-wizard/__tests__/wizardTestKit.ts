/**
 * [INPUT]
 * ../wizardShared (POS: 迁移向导翻译契约 TranslationFn)
 * ../../../../../../../../locales/en.json (POS: 英文文案 SSOT)
 *
 * [OUTPUT]
 * t: 按英文语言包解析 memory.migrationWizard 键并替换 {name} 插值的翻译函数；dryRun: 粘贴来源的 dry-run 样例。
 *
 * [POS]
 * 迁移向导测试共用夹具。步骤组件通过 `t` 属性取文案，测试用同一份语言包解析，断言的就是用户看到的英文句子。
 */
import en from '../../../../../../../../locales/en.json';
import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import type { TranslationFn } from '../wizardShared';

const wizardMessages = en.memory.migrationWizard as unknown as Record<string, unknown>;

const readCopy = (key: string): string | null => {
  const copy = key
    .split('.')
    .reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      wizardMessages,
    );
  return typeof copy === 'string' ? copy : null;
};

export const t: TranslationFn = (key, values) => {
  const copy = readCopy(key);
  if (copy === null) {
    return key;
  }
  return values ? copy.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? `{${name}}`)) : copy;
};

export const dryRun: MemoryImportDryRunResponse = {
  dry_run_id: 'memory-import:test',
  payload_hash: 'hash',
  expires_at: '2026-01-02T01:00:00Z',
  result: {
    summary: {
      source: 'pasted_memory',
      version: '1',
      total_items: 2,
      mapped_items: 1,
      unmapped_items: 1,
      status: 'warning',
    },
    mappings: [],
    warnings: ['pasted_entries_over_limit', 'brand_new_warning_code'],
    normalized_data: { conversation: [{ content: 'We settled on Postgres 17' }] },
  },
  pending_skills: [],
  pending_skills_total: 0,
  coverage_items: [],
  migration_lanes: [],
};
