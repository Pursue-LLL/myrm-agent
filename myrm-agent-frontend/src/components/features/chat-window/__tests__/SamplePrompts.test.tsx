/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ActionMode, AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { useProgressionStore } from '@/store/useProgressionStore';
import { elapse, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

import SamplePrompts from '../SamplePrompts';

// The global test setup translates a message key to itself, so the picked prompts read as their keys.
type Slot = 'morning' | 'afternoon' | 'evening' | 'night';

const agentConfigWith = (overrides: Partial<AgentConfig>): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  ...overrides,
});

const AGENT_POOL = [...Array.from({ length: 12 }, (_, i) => `samplePrompts.agent_${i}`), 'samplePrompts.agent_pptx'];
const FAST_POOL = Array.from({ length: 12 }, (_, i) => `samplePrompts.fast_${i}`);

/** The component reads local `getHours()`, so the fake clock is built from local components. */
function setClock(hour: number, minute = 0, second = 0) {
  vi.setSystemTime(new Date(2026, 10, 9, hour, minute, second));
}

const tab = (label: Slot | 'all') => screen.getByRole('button', { name: `lifeOperator.${label}` });
const isTabSelected = (label: Slot | 'all') => tab(label).classList.contains('bg-primary/15');
const hasCurrentTimeDot = (label: Slot) => tab(label).querySelector('.animate-pulse') !== null;

/** Prompt cards are every button that is not a time-slot tab, in display order. */
const promptCards = (): HTMLElement[] =>
  screen.getAllByRole('button').filter((button) => !(button.textContent ?? '').startsWith('lifeOperator.'));

const cardTexts = (): string[] => promptCards().map((card) => card.textContent ?? '');

const timeSlotCards = (slot: Slot) => [0, 1, 2, 3].map((i) => `samplePrompts.time_${slot}_${i}`);

describe('SamplePrompts', () => {
  beforeEach(() => {
    startFakeClock();
    setClock(13);
    useChatStore.setState({ actionMode: 'agent', inputMessage: '', agentConfig: null });
    useProgressionStore.setState({ currentLevel: 1 });
  });

  afterEach(() => {
    stopFakeClock();
  });

  describe('time of day', () => {
    it.each<[hour: number, minute: number, slot: Slot]>([
      [0, 0, 'night'],
      [5, 59, 'night'],
      [6, 0, 'morning'],
      [11, 59, 'morning'],
      [12, 0, 'afternoon'],
      [17, 59, 'afternoon'],
      [18, 0, 'evening'],
      [23, 59, 'evening'],
    ])('at %i:%i recommends the %s prompts and marks that tab as the current time', (hour, minute, slot) => {
      setClock(hour, minute);
      render(<SamplePrompts />);

      expect(cardTexts()).toEqual(timeSlotCards(slot));
      expect(isTabSelected(slot)).toBe(true);
      expect(document.querySelectorAll('.animate-pulse')).toHaveLength(1);
      expect(hasCurrentTimeDot(slot)).toBe(true);
    });

    it('renders the server markup for the morning set, then switches to the real slot once mounted', () => {
      setClock(15);
      expect(renderToString(<SamplePrompts />)).toContain('samplePrompts.time_morning_0');

      render(<SamplePrompts />);

      expect(cardTexts()).toEqual(timeSlotCards('afternoon'));
    });

    it('moves the recommendation when the hour changes while the page stays open', async () => {
      setClock(11, 59, 30);
      render(<SamplePrompts />);
      expect(cardTexts()).toEqual(timeSlotCards('morning'));

      await elapse(60_000);

      expect(cardTexts()).toEqual(timeSlotCards('afternoon'));
      expect(isTabSelected('afternoon')).toBe(true);
    });

    it('stops watching the clock after it unmounts', () => {
      const { unmount } = render(<SamplePrompts />);
      expect(vi.getTimerCount()).toBe(1);

      unmount();

      expect(vi.getTimerCount()).toBe(0);
    });
  });

  describe('slot tabs', () => {
    it('shows another slot on request and returns to the automatic one when the current tab is clicked', async () => {
      setClock(17, 59, 30);
      render(<SamplePrompts />);

      fireEvent.click(tab('morning'));
      expect(cardTexts()).toEqual(timeSlotCards('morning'));
      expect(isTabSelected('morning')).toBe(true);
      expect(isTabSelected('afternoon')).toBe(false);
      expect(hasCurrentTimeDot('afternoon')).toBe(true);

      fireEvent.click(tab('afternoon'));
      expect(cardTexts()).toEqual(timeSlotCards('afternoon'));
      expect(isTabSelected('afternoon')).toBe(true);
      expect(isTabSelected('morning')).toBe(false);

      // Back on the automatic recommendation, so it follows the clock into the next slot.
      await elapse(60_000);
      expect(cardTexts()).toEqual(timeSlotCards('evening'));
    });

    it('draws four distinct prompts from the agent pool for "all", the same four every time', () => {
      const firstView = render(<SamplePrompts />);
      fireEvent.click(tab('all'));

      const first = cardTexts();
      expect(new Set(first).size).toBe(4);
      first.forEach((text) => expect(AGENT_POOL).toContain(text));
      expect(isTabSelected('all')).toBe(true);
      expect(isTabSelected('afternoon')).toBe(false);

      firstView.unmount();
      render(<SamplePrompts />);
      fireEvent.click(tab('all'));
      expect(cardTexts()).toEqual(first);
    });

    it('draws from the fast pool in fast mode and never mixes the two pools', () => {
      useChatStore.setState({ actionMode: 'fast' });
      render(<SamplePrompts />);
      fireEvent.click(tab('all'));

      cardTexts().forEach((text) => expect(FAST_POOL).toContain(text));
    });

    it.each<[ActionMode, string[]]>([
      ['agent', AGENT_POOL],
      ['fast', FAST_POOL],
    ])(
      'rotates through every %s prompt across agents, each with its own icon, so none is dropped from the pool',
      (actionMode, pool) => {
        useChatStore.setState({ actionMode });
        const seen = new Set<string>();

        for (let agent = 0; agent < 40; agent += 1) {
          useChatStore.setState({ agentConfig: agentConfigWith({ agentId: `agent-${agent}` }) });
          const view = render(<SamplePrompts />);
          fireEvent.click(tab('all'));
          cardTexts().forEach((text) => seen.add(text));
          promptCards().forEach((card) => expect(card.querySelector('svg')).not.toBeNull());
          view.unmount();
        }

        expect([...seen].sort()).toEqual([...pool].sort());
      },
    );

    it('treats an action mode it has no prompts for as agent mode', () => {
      useChatStore.setState({ actionMode: 'retired-mode' as unknown as ActionMode });
      render(<SamplePrompts />);
      fireEvent.click(tab('all'));

      expect(cardTexts()).toHaveLength(4);
      cardTexts().forEach((text) => expect(AGENT_POOL).toContain(text));
    });

    it('offers a different set to a different agent, and the same set whatever the user level', () => {
      const picksFor = (agentId: string, level: number) => {
        useChatStore.setState({ agentConfig: agentConfigWith({ agentId }) });
        useProgressionStore.setState({ currentLevel: level });
        const view = render(<SamplePrompts />);
        fireEvent.click(tab('all'));
        const picks = cardTexts();
        view.unmount();
        return picks;
      };

      const byAgent = new Set(['a', 'b', 'c', 'd', 'e', 'f'].map((id) => picksFor(id, 1).join('|')));
      const byLevel = new Set([1, 2, 3, 4, 5].map((level) => picksFor('a', level).join('|')));

      expect(byAgent.size).toBeGreaterThan(1);
      // The progression loads after the first paint; the cards on screen must not reshuffle when it arrives.
      expect(byLevel.size).toBe(1);
    });
  });

  describe("an agent's own suggestions", () => {
    const suggestions = ['custom A', 'custom B', 'custom C', 'custom D', 'custom E'];

    it('replaces the tabs and the built-in prompts with four of the suggestions', () => {
      useChatStore.setState({ agentConfig: agentConfigWith({ agentId: 'writer', suggestionPrompts: suggestions }) });
      render(<SamplePrompts />);

      expect(screen.queryByRole('button', { name: /^lifeOperator\./ })).toBeNull();
      const shown = cardTexts();
      expect(new Set(shown).size).toBe(4);
      shown.forEach((text) => expect(suggestions).toContain(text));
    });

    it('shows every suggestion when there are fewer than four', () => {
      useChatStore.setState({ agentConfig: agentConfigWith({ suggestionPrompts: ['only one', 'and two'] }) });
      render(<SamplePrompts />);

      expect([...cardTexts()].sort()).toEqual(['and two', 'only one']);
    });

    it('falls back to the built-in prompts and tabs when the list is empty', () => {
      useChatStore.setState({ agentConfig: agentConfigWith({ suggestionPrompts: [] }) });
      render(<SamplePrompts />);

      expect(cardTexts()).toEqual(timeSlotCards('afternoon'));
      expect(tab('all')).toBeInTheDocument();
    });
  });

  describe('using a prompt', () => {
    it('puts the prompt text into the composer when its card is clicked', () => {
      render(<SamplePrompts />);

      fireEvent.click(screen.getByRole('button', { name: 'samplePrompts.time_afternoon_2' }));

      expect(useChatStore.getState().inputMessage).toBe('samplePrompts.time_afternoon_2');
    });

    it('puts a custom suggestion into the composer unchanged', () => {
      useChatStore.setState({ agentConfig: agentConfigWith({ suggestionPrompts: ['Plan my launch week'] }) });
      render(<SamplePrompts />);

      fireEvent.click(screen.getByRole('button', { name: 'Plan my launch week' }));

      expect(useChatStore.getState().inputMessage).toBe('Plan my launch week');
    });
  });
});
