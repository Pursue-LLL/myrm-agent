/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SkillsSectionPanel } from '../SkillsSectionPanel';
import type { Skill } from '@/store/skill/types';

describe('SkillsSectionPanel', () => {
  const mockSkills: Skill[] = [
    {
      id: 'skill-1',
      name: 'code_runner',
      description: 'Run python code',
      is_active: true,
      agent_id: 'test-agent',
    } as Skill,
    {
      id: 'skill-2',
      name: 'pdf_extractor',
      description: 'Extract PDF text',
      is_active: true,
      agent_id: 'test-agent',
    } as Skill,
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
});
