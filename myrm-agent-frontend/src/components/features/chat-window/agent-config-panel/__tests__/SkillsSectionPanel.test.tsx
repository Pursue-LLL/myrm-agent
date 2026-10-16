/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { AbstractIntlMessages } from 'next-intl';
import { SkillsSectionPanel } from '../SkillsSectionPanel';
import type { Skill } from '@/store/skill/types';
import en from '../../../../../../locales/en.json';
import zh from '../../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; the gauge-copy test below needs the real one.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

type Translate = (key: string, values?: Record<string, string | number>) => string;

// `useTranslations` is untyped in the app, so the panel props take free-form keys; mirror that here.
const translatorFor = (locale: string, messages: AbstractIntlMessages, namespace: string): Translate =>
  createTranslator({ locale, messages, namespace }) as Translate;

describe('SkillsSectionPanel', () => {
  const mockSkills: Skill[] = [
    {
      id: 'skill-1',
      name: 'code_runner',
      description: 'Run python code',
      agent_id: 'test-agent',
    } as unknown as Skill,
    {
      id: 'skill-2',
      name: 'pdf_extractor',
      description: 'Extract PDF text',
      agent_id: 'test-agent',
    } as unknown as Skill,
  ];

  const defaultProps = {
    enabledSkills: mockSkills,
    agentId: 'test-agent',
    localSkillIds: [] as string[],
    setLocalSkillIds: vi.fn(),
    localSkillConfigs: {},
    setLocalSkillConfigs: vi.fn(),
    noiseData: {
      isNoiseHigh: false,
      isNoiseCritical: false,
      noiseLevel: 10,
      coreSkillsTokenCost: 100,
      maxCoreTokens: 2000,
    },
    staleCoreSkills: [],
    onSmartPrune: vi.fn(),
    onOpenSettingsSheet: vi.fn(),
    t: (key: string) => key,
    tPanel: (key: string) => key,
  };

  it('renders pure instruction notice and select all button when no skills equipped', () => {
    render(<SkillsSectionPanel {...defaultProps} localSkillIds={[]} />);

    expect(screen.getByText('(skillsZone.pureInstructionNotice)')).toBeDefined();
    expect(screen.getByText('skillsZone.emptyExplanation')).toBeDefined();
    expect(screen.getByRole('button', { name: 'skillsZone.selectAll' })).toBeDefined();
    expect(screen.queryByRole('button', { name: 'skillsZone.clearAll' })).toBeNull();
  });

  it('calls setLocalSkillIds and setLocalSkillConfigs when select all is clicked', () => {
    const setLocalSkillIds = vi.fn();
    const setLocalSkillConfigs = vi.fn();

    render(
      <SkillsSectionPanel
        {...defaultProps}
        localSkillIds={[]}
        setLocalSkillIds={setLocalSkillIds}
        setLocalSkillConfigs={setLocalSkillConfigs}
      />,
    );

    const selectAllBtn = screen.getByRole('button', { name: 'skillsZone.selectAll' });
    fireEvent.click(selectAllBtn);

    expect(setLocalSkillIds).toHaveBeenCalledWith(['skill-1', 'skill-2']);
    expect(setLocalSkillConfigs).toHaveBeenCalled();
  });

  it('renders clear all button and hides select all when all skills equipped', () => {
    render(<SkillsSectionPanel {...defaultProps} localSkillIds={['skill-1', 'skill-2']} />);

    expect(screen.queryByText('(skillsZone.pureInstructionNotice)')).toBeNull();
    expect(screen.queryByText('skillsZone.emptyExplanation')).toBeNull();
    expect(screen.queryByRole('button', { name: 'skillsZone.selectAll' })).toBeNull();
    expect(screen.getByRole('button', { name: 'skillsZone.clearAll' })).toBeDefined();
  });

  it('calls clearAll to reset skill IDs and configs', () => {
    const setLocalSkillIds = vi.fn();
    const setLocalSkillConfigs = vi.fn();

    render(
      <SkillsSectionPanel
        {...defaultProps}
        localSkillIds={['skill-1', 'skill-2']}
        setLocalSkillIds={setLocalSkillIds}
        setLocalSkillConfigs={setLocalSkillConfigs}
      />,
    );

    const clearAllBtn = screen.getByRole('button', { name: 'skillsZone.clearAll' });
    fireEvent.click(clearAllBtn);

    expect(setLocalSkillIds).toHaveBeenCalledWith([]);
    expect(setLocalSkillConfigs).toHaveBeenCalledWith({});
  });

  // The gauge copy lives in `agent.configEditor`; wiring it to the `agent.configPanel` translator renders raw key paths.
  it.each([
    ['en', en],
    ['zh', zh],
  ])('phrases the action-space gauge from the real %s messages', (locale, messages) => {
    const t = translatorFor(locale, messages, 'agent.configEditor');
    const tPanel = translatorFor(locale, messages, 'agent.configPanel');
    const radar = messages.agent.configEditor.actionSpaceRadar;

    render(
      <SkillsSectionPanel
        {...defaultProps}
        t={t}
        tPanel={tPanel}
        noiseData={{ ...defaultProps.noiseData, isNoiseHigh: true }}
        staleCoreSkills={['code_runner', 'pdf_extractor']}
      />,
    );

    expect(screen.getByText(radar.loadMeterLabel)).toBeDefined();
    expect(screen.getByText(radar.statusHigh)).toBeDefined();
    expect(screen.getByText(radar.staleSkillsNotice.replace('{count}', '2'))).toBeDefined();
    expect(screen.getByRole('button', { name: radar.smartPrune })).toBeDefined();
  });
});
