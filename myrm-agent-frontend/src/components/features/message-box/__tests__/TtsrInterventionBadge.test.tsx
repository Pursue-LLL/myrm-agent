/**
 * [INPUT]
 * - components/features/message-box/TtsrInterventionBadge::TtsrInterventionBadge (POS: 实时安全拦截提示徽章组件)
 * 
 * [OUTPUT]
 * - TtsrInterventionBadge.test.tsx: 验证徽章组件渲染、安全防护标签、展开指引与重试文案
 * 
 * [POS]
 * 单元测试层。验证消息气泡中的 TTSR 动态防御徽章交互行为及 DOM 语义化输出。
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import {
  TtsrInterventionBadge,
  groupTtsrInterventions,
  type TtsrInterventionItem,
} from '../TtsrInterventionBadge';

describe('groupTtsrInterventions', () => {
  it('handles nullish or empty intervention lists gracefully', () => {
    expect(groupTtsrInterventions(null)).toEqual([]);
    expect(groupTtsrInterventions(undefined)).toEqual([]);
    expect(groupTtsrInterventions([])).toEqual([]);
  });

  it('groups multiple occurrences of the same ruleId and tracks history', () => {
    const rawItems: TtsrInterventionItem[] = [
      {
        ruleId: 'ban_rm',
        ruleName: 'Ban Rm',
        reminder: 'First attempt warning',
        retryCount: 1,
        maxRetries: 2,
        timestamp: '2026-09-28T10:00:00Z',
      },
      {
        ruleId: 'ban_rm',
        ruleName: 'Ban Rm',
        reminder: 'Second attempt warning',
        retryCount: 2,
        maxRetries: 2,
        timestamp: '2026-09-28T10:00:02Z',
      },
      {
        ruleId: 'ban_leak',
        ruleName: 'Ban Leak',
        reminder: 'Leak detected',
        retryCount: 1,
        maxRetries: 2,
      },
    ];

    const grouped = groupTtsrInterventions(rawItems);
    expect(grouped).toHaveLength(2);

    const rmGroup = grouped.find((g) => g.ruleId === 'ban_rm');
    expect(rmGroup).toBeDefined();
    expect(rmGroup?.attemptsCount).toBe(2);
    expect(rmGroup?.retryCount).toBe(2);
    expect(rmGroup?.reminder).toBe('Second attempt warning');
    expect(rmGroup?.history).toHaveLength(2);

    const leakGroup = grouped.find((g) => g.ruleId === 'ban_leak');
    expect(leakGroup).toBeDefined();
    expect(leakGroup?.attemptsCount).toBe(1);
    expect(leakGroup?.history).toHaveLength(1);
  });
});

describe('TtsrInterventionBadge', () => {
  it('renders rule name, active defense badge, and retry indicator', () => {
    render(
      <TtsrInterventionBadge
        ruleId="ban_destructive_rm"
        ruleName="Ban Destructive Rm"
        reminder="Destructive rm commands are prohibited."
        target="assistant"
        retryCount={1}
        maxRetries={2}
      />
    );

    expect(screen.getByRole('status')).toBeDefined();
    expect(screen.getByText('Ban Destructive Rm')).toBeDefined();
    expect(screen.getByText('Active Defense')).toBeDefined();
    expect(screen.getByText(/Auto-Corrected \(1\/2\)/i)).toBeDefined();
  });

  it('renders multi-attempt indicators and folded timeline in expanded view', () => {
    const history: TtsrInterventionItem[] = [
      {
        ruleId: 'ban_rm',
        ruleName: 'Ban Rm',
        reminder: 'Attempt 1 reminder',
        retryCount: 1,
        timestamp: '2026-09-28T10:00:00Z',
      },
      {
        ruleId: 'ban_rm',
        ruleName: 'Ban Rm',
        reminder: 'Attempt 2 reminder',
        retryCount: 2,
        timestamp: '2026-09-28T10:00:05Z',
      },
    ];

    render(
      <TtsrInterventionBadge
        ruleId="ban_rm"
        ruleName="Ban Rm"
        reminder="Attempt 2 reminder"
        retryCount={2}
        maxRetries={2}
        attemptsCount={2}
        history={history}
      />
    );

    expect(screen.getByText(/Auto-Corrected \(2\/2 · 2 attempts\)/i)).toBeDefined();

    const toggleBtn = screen.getByRole('button', { name: /View Safety Guidance/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText(/Intervention Timeline \(2 attempts\)/i)).toBeDefined();
    expect(screen.getByText(/Attempt #1 \(retry 1\)/i)).toBeDefined();
    expect(screen.getByText(/Attempt #2 \(retry 2\)/i)).toBeDefined();
  });

  it('expands and collapses guidance on toggle click', () => {
    render(
      <TtsrInterventionBadge
        ruleId="ban_leak"
        ruleName="Ban Secret Leak"
        reminder="Do not leak private tokens."
        target="tool_args"
      />
    );

    expect(screen.queryByText('Do not leak private tokens.')).toBeNull();

    const toggleBtn = screen.getByRole('button', { name: /View Safety Guidance/i });
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggleBtn);

    expect(screen.getByText('Do not leak private tokens.')).toBeDefined();
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText(/Protected Scope: Command & Execution Safety/i)).toBeDefined();

    // Collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByText('Do not leak private tokens.')).toBeNull();
  });
});

