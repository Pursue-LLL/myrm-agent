import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationalConfigActionCard } from '../ConversationalConfigActionCard';
import { ConversationalConfigIntent } from '../conversationalConfigTypes';
import { useConversationalConfigStore } from '../useConversationalConfigStore';

describe('ConversationalConfigActionCard', () => {
  beforeEach(() => {
    useConversationalConfigStore.getState().reset();
  });

  const mockCard: ConversationalConfigIntent = {
    id: 'mock-card-1',
    category: 'api_key_entry',
    title: 'OpenAI 凭据安全写入确认',
    description: '检测到凭据配置意图',
    matchedUtterance: '配置 openai key',
    params: [
      {
        key: 'provider',
        label: '服务供应商',
        type: 'text',
        value: 'OpenAI',
      },
      {
        key: 'api_key',
        label: 'API 授权凭据',
        type: 'password',
        value: 'sk-1234567890',
        placeholder: 'sk-...',
        isSecret: true,
      },
    ],
    isApplied: false,
    createdAt: Date.now(),
  };

  it('renders card title, description, and inputs correctly', () => {
    useConversationalConfigStore.getState().addConfigCard(mockCard);
    render(<ConversationalConfigActionCard card={mockCard} />);

    expect(screen.getByText('OpenAI 凭据安全写入确认')).toBeDefined();
    expect(screen.getByText('检测到凭据配置意图')).toBeDefined();
    expect(screen.getByDisplayValue('OpenAI')).toBeDefined();
    expect(screen.getByDisplayValue('sk-1234567890')).toBeDefined();
  });

  it('toggles password visibility when eye button is clicked', () => {
    useConversationalConfigStore.getState().addConfigCard(mockCard);
    render(<ConversationalConfigActionCard card={mockCard} />);

    const eyeButton = screen.getByLabelText('显示秘钥明文');
    expect(eyeButton).toBeDefined();

    const input = screen.getByLabelText('API 授权凭据') as HTMLInputElement;
    expect(input.type).toBe('password');

    fireEvent.click(eyeButton);
    expect(input.type).toBe('text');
    expect(screen.getByLabelText('隐藏秘钥明文')).toBeDefined();

    fireEvent.click(screen.getByLabelText('隐藏秘钥明文'));
    expect(input.type).toBe('password');
  });

  it('handles apply button click and triggers onApplied callback', () => {
    useConversationalConfigStore.getState().addConfigCard(mockCard);
    const onApplied = vi.fn();

    render(
      <ConversationalConfigActionCard
        card={mockCard}
        onApplied={onApplied}
      />,
    );

    const applyButton = screen.getByText('确认应用 (Apply)');
    fireEvent.click(applyButton);

    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(
      useConversationalConfigStore.getState().appliedConfigurations['api_key'],
    ).toBe('sk-1234567890');
  });

  it('displays applied indicator when card isApplied is true', () => {
    const appliedCard: ConversationalConfigIntent = {
      ...mockCard,
      isApplied: true,
    };
    render(<ConversationalConfigActionCard card={appliedCard} />);

    expect(screen.getByText('已成功应用配置')).toBeDefined();
    expect(screen.queryByText('确认应用 (Apply)')).toBeNull();
  });

  it('dismisses card when close button is clicked', () => {
    useConversationalConfigStore.getState().addConfigCard(mockCard);
    render(<ConversationalConfigActionCard card={mockCard} />);

    const closeButton = screen.getByLabelText('关闭配置卡片');
    fireEvent.click(closeButton);

    expect(
      useConversationalConfigStore.getState().activeConfigCards['mock-card-1'],
    ).toBeUndefined();
  });
});
