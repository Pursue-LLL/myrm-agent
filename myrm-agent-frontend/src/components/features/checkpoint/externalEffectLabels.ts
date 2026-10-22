import type { useTranslations } from 'next-intl';

/**
 * Plain-language labels for the external-effect categories the server records.
 *
 * [INPUT]
 * - `fileSnapshot` translator: owns the `effects.<category>` labels
 *
 * [OUTPUT]
 * - formatExternalEffects: category list -> comma-joined labels; an unknown category is shown as-is
 *
 * [POS]
 * 前端检查点特性层：文件快照与安全气囊共用的外部影响文案映射。
 */
export const formatExternalEffects = (effects: readonly string[], t: ReturnType<typeof useTranslations>): string =>
  effects.map((effect) => (t.has(`effects.${effect}`) ? t(`effects.${effect}`) : effect)).join(', ');
