import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SearchToolCard from '../SearchToolCard';
import useChatStore from '@/store/useChatStore';

// Mock next-intl
vi.mock('next-intl', () => {
  // Stable reference: a fresh translator per render re-triggers effects keyed on `t`.
  const t = (key: string, values?: Record<string, string | number>) => {
    const translations: Record<string, string> = {
      globLabel: '文件搜索',
      grepLabel: '内容搜索',
      path: '路径',
      filePattern: '文件',
      cacheHitTitle: '命中缓存快照',
      justNow: '刚刚',
      forceRefresh: '强制联网重新抓取',
      forceRefreshing: '正在穿透刷新...',
      scenarioRealtime: '实时动态',
      scenarioStandard: '标准业务',
      scenarioArchive: '静态归档',
    };
    if (key === 'savedTokens' && values?.count) {
      return `已为您节省 ${values.count} tokens`;
    }
    if (key === 'minutesAgo' && values?.count) {
      return `${values.count}分钟前`;
    }
    if (key === 'secondsAgo' && values?.count) {
      return `${values.count}秒前`;
    }
    return translations[key] || key;
  };
  return { useTranslations: () => t };
});

describe('SearchToolCard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders standard uncached search item properly', () => {
    render(
      <SearchToolCard
        items={[
          {
            pattern: 'useAuthToken',
            search_path: 'src/hooks',
            file_pattern: '*.ts',
            scenario: 'standard',
          },
        ]}
        toolName="grep_tool"
        messageId="msg-1"
        stepIndex={0}
      />,
    );

    expect(screen.getByText('内容搜索')).toBeDefined();
    expect(screen.getByText('useAuthToken')).toBeDefined();
    expect(screen.getByText('src/hooks')).toBeDefined();
    expect(screen.getByText('*.ts')).toBeDefined();
    expect(screen.getByText('标准业务 (30m)')).toBeDefined();
    // Cache badge should NOT be visible
    expect(screen.queryByText(/命中缓存快照/)).toBeNull();
  });

  it('renders cache hit badge with savings and scenario for cached search', () => {
    render(
      <SearchToolCard
        items={[
          {
            pattern: 'BTC/USDT 实时行情',
            search_path: '.',
            cached: true,
            cache_age_seconds: 180,
            saved_tokens: 3200,
            scenario: 'realtime',
          },
        ]}
        toolName="grep_tool"
        messageId="msg-2"
        stepIndex={1}
      />,
    );

    expect(screen.getByText('实时动态 (3m)')).toBeDefined();
    expect(screen.getByText(/命中缓存快照/)).toBeDefined();
    expect(screen.getByText(/3分钟前/)).toBeDefined();
    expect(screen.getByText(/已为您节省 3,200 tokens/)).toBeDefined();
    expect(screen.getByRole('button', { name: /强制联网重新抓取/ })).toBeDefined();
  });

  it('triggers onForceRefresh callback and enters refreshing state on button click', () => {
    const handleForceRefresh = vi.fn();
    const mockItem = {
      pattern: 'RFC 9110 HTTP',
      cached: true,
      cache_age_seconds: 7200,
      saved_tokens: 1500,
      scenario: 'archive' as const,
    };

    render(
      <SearchToolCard
        items={[mockItem]}
        toolName="glob_tool"
        messageId="msg-3"
        stepIndex={2}
        onForceRefresh={handleForceRefresh}
      />,
    );

    expect(screen.getByText('静态归档 (24h)')).toBeDefined();
    const refreshBtn = screen.getByRole('button', { name: /强制联网重新抓取/ });
    fireEvent.click(refreshBtn);

    expect(handleForceRefresh).toHaveBeenCalledTimes(1);
    expect(handleForceRefresh).toHaveBeenCalledWith(mockItem);
    expect(screen.getByText('正在穿透刷新...')).toBeDefined();
  });

  it('falls back to useChatStore.sendMessage when onForceRefresh is not provided', () => {
    const sendMessageMock = vi.fn();
    vi.spyOn(useChatStore, 'getState').mockReturnValue({
      sendMessage: sendMessageMock,
    } as unknown as ReturnType<typeof useChatStore.getState>);

    render(
      <SearchToolCard
        items={[
          {
            pattern: 'ETH gas tracker',
            cached: true,
            cache_age_seconds: 10,
            saved_tokens: 800,
            scenario: 'realtime',
          },
        ]}
        toolName="grep_tool"
        messageId="msg-4"
        stepIndex={3}
      />,
    );

    const refreshBtn = screen.getByRole('button', { name: /强制联网重新抓取/ });
    fireEvent.click(refreshBtn);

    expect(sendMessageMock).toHaveBeenCalledWith('[force_refresh] ETH gas tracker');
  });
});
