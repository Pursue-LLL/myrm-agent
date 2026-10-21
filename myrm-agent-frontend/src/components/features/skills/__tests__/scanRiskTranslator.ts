import { vi } from 'vitest';

import type { ScanRiskTranslate } from '@/lib/skills/scanRiskText';
import en from '../../../../../locales/en.json';

// The global test setup replaces next-intl, so the real translator is loaded explicitly: card tests then assert on the
// shipped English scan wording instead of a hand-written copy that could drift from it.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

export const SCAN_RISK_NAMESPACE = 'settings.skills.scanRisk';

/** The English `settings.skills.scanRisk` translator the skill review cards read their scan wording from. */
export const scanRiskT = createTranslator({
  locale: 'en',
  messages: en,
  namespace: SCAN_RISK_NAMESPACE,
}) as unknown as ScanRiskTranslate;
