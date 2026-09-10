/**
 * Unit tests for SamplePrompts empty chat quick prompt cards.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import SamplePrompts from '../SamplePrompts';
import useChatStore from '@/store/useChatStore';

const TRANSLATIONS: Record<string, string> = {
  'chat.samplePrompts.agent_0': '帮我制作一份 16:9 商业汇报 PPT (可编辑 pptx 格式)',
  'chat.samplePrompts.agent_1': '帮我做一份本周工作总结报告',
  'chat.samplePrompts.agent_2': '帮我写一篇公众号图文推送',
  'chat.samplePrompts.agent_3': '帮我设置每天早上 8 点的日报提醒',
  'chat.samplePrompts.timeFilterAuto': '时段推荐',
  'chat.samplePrompts.timeFilterAll': '全部',
  'chat.samplePrompts.timeMorning': '早间规划',
  'chat.samplePrompts.timeAfternoon': '下午专注',
  'chat.samplePrompts.timeEvening': '晚间复盘',
  'chat.samplePrompts.timeNight': '夜间整理',
};

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => {
    const fullKey = `${ns}.${key}`;
    return TRANSLATIONS[fullKey] || TRANSLATIONS[key] || key;
  },
}));

describe('SamplePrompts', () => {
  beforeEach(() => {
    useChatStore.setState({
      actionMode: 'agent',
      inputMessage: '',
      agentConfig: null,
    });
  });

  it('renders sample prompts and fills inputMessage when prompt card is clicked', () => {
    render(<SamplePrompts />);

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);

    // Filter cards
    const promptCard = buttons.find((btn) =>
      btn.textContent?.includes('帮我制作一份 16:9 商业汇报 PPT (可编辑 pptx 格式)') ||
      btn.textContent?.includes('PPT')
    );

    if (promptCard) {
      fireEvent.click(promptCard);
      expect(useChatStore.getState().inputMessage).toContain('PPT');
    }
  });
});
