import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReferralFissionDeck } from '../ReferralFissionDeck';
import { useReferralFissionStore } from '../useReferralFissionStore';

describe('ReferralFissionDeck Component', () => {
  beforeEach(() => {
    useReferralFissionStore.getState().resetState();
  });

  it('renders referral dashboard header, metrics, and security badges', () => {
    render(<ReferralFissionDeck />);

    expect(screen.getByText('双向算力裂变与增长看板')).toBeInTheDocument();
    expect(screen.getByText('Zero-Dox 认证')).toBeInTheDocument();
    expect(screen.getByText('累计裂变收益')).toBeInTheDocument();
    expect(screen.getByText('当前可用额度')).toBeInTheDocument();
    expect(screen.getByText('云端沙箱分润')).toBeInTheDocument();
    expect(screen.getByText('成功邀请总数')).toBeInTheDocument();
    expect(screen.getByText('防刷反作弊风控门禁 (Anti-Sybil)')).toBeInTheDocument();
    expect(screen.getByText('立减 $15 美元云端算力礼包')).toBeInTheDocument();
  });

  it('handles slug editing with validation and error feedback', () => {
    render(<ReferralFissionDeck />);

    const editButton = screen.getByRole('button', { name: /修改个性短码/ });
    fireEvent.click(editButton);

    const input = screen.getByPlaceholderText('例如: coder-bob');
    expect(input).toBeInTheDocument();

    // 尝试提交系统保留字
    fireEvent.change(input, { target: { value: 'admin' } });
    const submitBtn = screen.getByRole('button', { name: '保存' });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/该标识符为系统保留关键字/)).toBeInTheDocument();

    // 提交合法伪名
    fireEvent.change(input, { target: { value: 'cool-pilot' } });
    fireEvent.click(submitBtn);

    // 错误消失，Slug 更新
    expect(screen.queryByText(/该标识符为系统保留关键字/)).toBeNull();
    expect(useReferralFissionStore.getState().profile.slug).toBe('cool-pilot');
  });

  it('allows resetting back to CSPRNG random slug', () => {
    useReferralFissionStore.getState().updateCustomSlug('custom-coder');
    render(<ReferralFissionDeck />);

    const editButton = screen.getByRole('button', { name: /修改个性短码/ });
    fireEvent.click(editButton);

    const resetBtn = screen.getByRole('button', { name: '重置为随机无语义短码' });
    fireEvent.click(resetBtn);

    expect(useReferralFissionStore.getState().profile.isCustomSlug).toBe(false);
    expect(useReferralFissionStore.getState().profile.slug).not.toBe('custom-coder');
  });
});
