'use client';

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import SamplePrompts from '../SamplePrompts';

const mockSetInputMessage = vi.fn();

const translations: Record<string, string> = {
  'samplePrompts.time_morning_0': 'Morning Key Priority 0',
  'samplePrompts.time_morning_1': 'Morning Key Priority 1',
  'samplePrompts.time_morning_2': 'Morning Key Priority 2',
  'samplePrompts.time_morning_3': 'Morning Key Priority 3',
  'samplePrompts.time_afternoon_0': 'Afternoon Sprint 0',
  'samplePrompts.time_afternoon_1': 'Afternoon Sprint 1',
  'samplePrompts.time_afternoon_2': 'Afternoon Sprint 2',
  'samplePrompts.time_afternoon_3': 'Afternoon Sprint 3',
  'samplePrompts.time_evening_0': 'Evening Retro 0',
  'samplePrompts.time_evening_1': 'Evening Retro 1',
  'samplePrompts.time_evening_2': 'Evening Retro 2',
  'samplePrompts.time_evening_3': 'Evening Retro 3',
  'samplePrompts.time_night_0': 'Night Deep Work 0',
  'samplePrompts.time_night_1': 'Night Deep Work 1',
  'samplePrompts.time_night_2': 'Night Deep Work 2',
  'samplePrompts.time_night_3': 'Night Deep Work 3',
  'samplePrompts.agent_0': 'Agent Prompt 0',
  'samplePrompts.fast_0': 'Fast Prompt 0',
  'lifeOperator.morning': 'Morning Focus',
  'lifeOperator.afternoon': 'Afternoon Sprint',
  'lifeOperator.evening': 'Evening Retro',
  'lifeOperator.night': 'Night Deep Work',
  'lifeOperator.all': 'Explore All',
};

const stableT = (key: string) => translations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  __esModule: true,
  default: (selector: (state: unknown) => unknown) => {
    const state = {
      actionMode: 'agent',
      setInputMessage: mockSetInputMessage,
      agentConfig: null,
    };
    return selector(state);
  },
}));

vi.mock('@/store/useProgressionStore', () => ({
  useProgressionStore: (selector: (state: unknown) => unknown) => {
    const state = {
      currentLevel: 1,
    };
    return selector(state);
  },
}));

describe('SamplePrompts with Context-Aware Life Operator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders time slot tabs and prompt chips', () => {
    render(<SamplePrompts />);
    expect(screen.getByText('Morning Focus')).toBeInTheDocument();
    expect(screen.getByText('Afternoon Sprint')).toBeInTheDocument();
    expect(screen.getByText('Evening Retro')).toBeInTheDocument();
    expect(screen.getByText('Night Deep Work')).toBeInTheDocument();
    expect(screen.getByText('Explore All')).toBeInTheDocument();
  });

  it('switches time slots and updates displayed prompts when clicking tabs', () => {
    render(<SamplePrompts />);

    // Click Afternoon tab
    fireEvent.click(screen.getByText('Afternoon Sprint'));
    expect(screen.getByText('Afternoon Sprint 0')).toBeInTheDocument();
    expect(screen.getByText('Afternoon Sprint 1')).toBeInTheDocument();

    // Click Evening tab
    fireEvent.click(screen.getByText('Evening Retro'));
    expect(screen.getByText('Evening Retro 0')).toBeInTheDocument();
    expect(screen.getByText('Evening Retro 1')).toBeInTheDocument();
  });

  it('injects structured prompt into chat store input message when prompt chip clicked', () => {
    render(<SamplePrompts />);

    // Click Afternoon tab
    fireEvent.click(screen.getByText('Afternoon Sprint'));
    const chip = screen.getByText('Afternoon Sprint 0');
    fireEvent.click(chip);

    expect(mockSetInputMessage).toHaveBeenCalledWith('Afternoon Sprint 0');
  });
});
