import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LocalFirstPrivacySandboxCard } from '../LocalFirstPrivacySandboxCard';
import { useLocalFirstStore } from '../useLocalFirstStore';

describe('LocalFirstPrivacySandboxCard', () => {
  beforeEach(() => {
    useLocalFirstStore.getState().reset();
  });

  it('renders card title, privacy badge, and controls accurately', () => {
    render(<LocalFirstPrivacySandboxCard />);

    expect(screen.getByTestId('local-first-privacy-sandbox-card')).toBeDefined();
    expect(screen.getByText('纯客户端隐私沙盒')).toBeDefined();
    expect(screen.getByText(/100% 离线计算 · 零网络上传/)).toBeDefined();
    expect(screen.getByText('本地脱敏 (Zero-Upload)')).toBeDefined();
    expect(screen.getByLabelText('漫游存储引擎')).toBeDefined();
  });

  it('performs zero-upload sanitize on button click and calls onSanitized', () => {
    const onSanitized = vi.fn();
    render(<LocalFirstPrivacySandboxCard onSanitized={onSanitized} />);

    const textarea = screen.getByLabelText('待处理文本或 JSON 数据:');
    fireEvent.change(textarea, {
      target: { value: '我的手机号 13812345678 勿泄露' },
    });

    const sanitizeBtn = screen.getByText('本地脱敏 (Zero-Upload)');
    fireEvent.click(sanitizeBtn);

    expect(onSanitized).toHaveBeenCalledWith(1);
    expect(screen.getByDisplayValue('我的手机号 138****5678 勿泄露')).toBeDefined();
    expect(screen.getByText(/已脱敏 1 处敏感信息/)).toBeDefined();
  });

  it('switches storage backend using select dropdown', () => {
    render(<LocalFirstPrivacySandboxCard />);

    const select = screen.getByLabelText('漫游存储引擎');
    fireEvent.change(select, { target: { value: 'upstash_redis' } });

    expect(useLocalFirstStore.getState().activeBackend).toBe('upstash_redis');
  });

  it('performs format conversion on button click', () => {
    render(<LocalFirstPrivacySandboxCard />);

    const textarea = screen.getByLabelText('待处理文本或 JSON 数据:');
    const sampleJson = JSON.stringify([{ id: 101, title: 'Item' }]);
    fireEvent.change(textarea, { target: { value: sampleJson } });

    const csvBtn = screen.getByText('csv');
    fireEvent.click(csvBtn);

    expect(screen.getByText(/id,title/)).toBeDefined();
    expect(screen.getByText(/101,Item/)).toBeDefined();
  });

  it('shows error message when format convert encounters invalid json', () => {
    render(<LocalFirstPrivacySandboxCard />);

    const textarea = screen.getByLabelText('待处理文本或 JSON 数据:');
    fireEvent.change(textarea, { target: { value: '{ invalid json }' } });

    const csvBtn = screen.getByText('csv');
    fireEvent.click(csvBtn);

    expect(screen.getByText('无效的 JSON 格式，请检查语法')).toBeDefined();
  });
});
