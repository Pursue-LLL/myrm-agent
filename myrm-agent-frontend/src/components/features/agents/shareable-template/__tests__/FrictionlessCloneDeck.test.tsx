import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FrictionlessCloneDeck } from '../FrictionlessCloneDeck';
import { useShareableTemplateStore } from '../useShareableTemplateStore';
import type { BotTemplateEntity } from '../shareableTemplateTypes';

describe('FrictionlessCloneDeck', () => {
  beforeEach(() => {
    useShareableTemplateStore.getState().resetState();
  });

  const mockTemplate: BotTemplateEntity = {
    id: 'tpl-react-master',
    slug: 'react-master-bot',
    title: 'React Architecture Specialist',
    description: 'Specialized in React 19 and concurrent mode',
    authorHandle: '@dan_abramov_fan',
    avatarIconName: 'Bot',
    baseModel: 'claude-3-opus',
    systemPrompt: 'You are a principal frontend engineer.',
    requiredSkills: ['react-audit', 'vite-bundler'],
    environmentKeySlots: ['${GITHUB_ACCESS_TOKEN}'],
    createdAt: Date.now(),
  };

  it('renders nothing when isCloneDeckOpen is false', () => {
    const { container } = render(<FrictionlessCloneDeck />);
    expect(container.firstChild).toBeNull();
  });

  it('renders template details and fallback recommendations when model is missing', () => {
    const store = useShareableTemplateStore.getState();
    // 本地只有 qwen 和 deepseek，没有 claude-3-opus
    store.openCloneDeck(
      mockTemplate,
      ['qwen-2.5-72b', 'deepseek-v3'],
      ['vite-bundler'] // 缺失 react-audit
    );

    render(<FrictionlessCloneDeck />);

    expect(screen.getByText('一键克隆智能体')).toBeInTheDocument();
    expect(screen.getByText('React Architecture Specialist')).toBeInTheDocument();
    expect(screen.getByText('@dan_abramov_fan')).toBeInTheDocument();
    expect(screen.getAllByText('claude-3-opus').length).toBeGreaterThanOrEqual(1);

    // 推荐平替检查
    expect(screen.getByText(/本地环境未检测到底模/)).toBeInTheDocument();
    expect(screen.getByText('qwen-2.5-72b')).toBeInTheDocument();

    // 技能依赖状态
    expect(screen.getByText(/react-audit \(待装载\)/)).toBeInTheDocument();
    expect(screen.getByText('${GITHUB_ACCESS_TOKEN}')).toBeInTheDocument();
  });

  it('handles clone action and shows success screen', () => {
    const store = useShareableTemplateStore.getState();
    store.openCloneDeck(
      mockTemplate,
      ['claude-3-opus'],
      ['react-audit', 'vite-bundler']
    );

    render(<FrictionlessCloneDeck />);

    const cloneButton = screen.getByRole('button', { name: /一键克隆到本地/ });
    expect(cloneButton).toBeInTheDocument();

    fireEvent.click(cloneButton);

    expect(screen.getByText('克隆成功！')).toBeInTheDocument();
    expect(screen.getByText(/React Architecture Specialist \(已克隆\)/)).toBeInTheDocument();
  });
});
