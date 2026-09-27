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
import { TtsrInterventionBadge } from '../TtsrInterventionBadge';

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
