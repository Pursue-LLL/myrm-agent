import { describe, expect, it } from 'vitest';

import {
  anySelectionNeedsContributorNotice,
  isMuseSparkContributorModel,
  providerHasEnabledContributorModel,
  shouldShowContributorNotice,
} from '@/components/features/settings/model-service/opencode-contributor-utils';

describe('opencode-contributor-utils', () => {
  it('detects muse-spark contributor model ids', () => {
    expect(isMuseSparkContributorModel('muse-spark-1.2-contributor')).toBe(true);
    expect(isMuseSparkContributorModel('MUSE-SPARK-1.2-CONTRIBUTOR')).toBe(true);
    expect(isMuseSparkContributorModel('muse-spark-1.2')).toBe(false);
    expect(isMuseSparkContributorModel('deepseek-v4-flash')).toBe(false);
  });

  it('scopes contributor detection to opencode_go provider', () => {
    expect(
      providerHasEnabledContributorModel('opencode_go', ['muse-spark-1.2-contributor']),
    ).toBe(true);
    expect(providerHasEnabledContributorModel('openai', ['muse-spark-1.2-contributor'])).toBe(false);
    expect(providerHasEnabledContributorModel('opencode_go', ['deepseek-v4-flash'])).toBe(false);
  });

  it('detects contributor notice for bound selections', () => {
    expect(
      shouldShowContributorNotice({ providerId: 'opencode_go', model: 'muse-spark-1.2-contributor' }),
    ).toBe(true);
    expect(
      shouldShowContributorNotice({ providerId: 'openai', model: 'muse-spark-1.2-contributor' }),
    ).toBe(false);
    expect(anySelectionNeedsContributorNotice([null, { providerId: 'opencode_go', model: 'muse-spark-1.2-contributor' }])).toBe(
      true,
    );
  });
});
