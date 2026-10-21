/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../AgentCapabilitiesConsensusSection', () => ({
  ConsensusRefModels: () => <div data-testid="consensus-ref-models" />,
}));

import { MoaOverlaySection } from '../AgentCapabilitiesMoaOverlaySection';
import type { AgentCapabilitiesTabProps } from '../AgentCapabilitiesTab';
import type { useTranslations } from 'next-intl';

const t = stableT as unknown as ReturnType<typeof useTranslations>;

describe('AgentCapabilitiesMoaOverlaySection', () => {
  it('renders disabled switch when overlay is not enabled', () => {
    const setEngineParams = vi.fn();
    const editor = {
      engineParams: {},
      setEngineParams,
    } as unknown as AgentCapabilitiesTabProps['editor'];

    render(<MoaOverlaySection editor={editor} t={t} />);
    expect(screen.getByText('agent.moaOverlayTitle')).toBeDefined();
    expect(screen.queryByText('agent.moaOverlayFanout')).toBeNull();
  });

  it('renders fanout options including risk_triggered when overlay is enabled', () => {
    const setEngineParams = vi.fn();
    const editor = {
      engineParams: {
        moa_overlay: {
          enabled: true,
          fanout: 'risk_triggered',
        },
      },
      setEngineParams,
    } as unknown as AgentCapabilitiesTabProps['editor'];

    render(<MoaOverlaySection editor={editor} t={t} />);
    expect(screen.getByText('agent.moaOverlayFanout')).toBeDefined();
    expect(screen.getByText('agent.moaOverlayFanoutRiskTriggered')).toBeDefined();
  });

  it('verifies moaOverlayFanoutRiskTriggered translation exists in all 6 supported locales', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const locales = ['zh', 'en', 'zh-TW', 'ja', 'de', 'ko'];
    for (const loc of locales) {
      const filePath = path.resolve(process.cwd(), `locales/${loc}.json`);
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      const text = content.agent?.moaOverlayFanoutRiskTriggered;
      expect(text, `Missing or empty moaOverlayFanoutRiskTriggered in locale: ${loc}`).toBeDefined();
      expect(typeof text).toBe('string');
      expect(text.trim().length).toBeGreaterThan(0);
    }
  });
});
