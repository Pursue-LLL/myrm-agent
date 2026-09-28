/** @vitest-environment jsdom */
'use client';

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CapabilitySurfaceMatrixGrid } from '../CapabilitySurfaceMatrixGrid';
import {
  deriveCapabilityMatrix,
  syncCapabilityActionToRules,
  CAPABILITY_SURFACES,
  CAPABILITY_PRESETS,
  type CapabilityMatrix,
} from '../securityPolicyUtils';

const stableT = (key: string, options?: { default?: string }) => options?.default ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('CapabilitySurfaceMatrixGrid Component', () => {
  const defaultMatrix: CapabilityMatrix = {
    knowledge_read: 'allow',
    knowledge_write: 'ask',
    web_egress: 'allow',
    candidate_create: 'allow',
    remote_tools: 'ask',
    local_filesystem: 'ask',
  };

  it('renders all 6 capability surfaces and their tool tags', () => {
    const handleChange = vi.fn();
    const handlePreset = vi.fn();

    render(<CapabilitySurfaceMatrixGrid matrix={defaultMatrix} onChange={handleChange} onApplyPreset={handlePreset} />);

    // 验证 6 大能力面全部呈现
    for (const surface of CAPABILITY_SURFACES) {
      expect(screen.getByText(surface.label)).toBeInTheDocument();
    }

    // 验证 wiki 相关工具标识存在
    expect(screen.getByText('wiki_query_tool')).toBeInTheDocument();
    expect(screen.getByText('wiki_apply_tool')).toBeInTheDocument();
    expect(screen.getByText('wiki_ingest_tool')).toBeInTheDocument();
  });

  it('triggers onChange when switching tri-state actions', () => {
    const handleChange = vi.fn();
    const handlePreset = vi.fn();

    render(<CapabilitySurfaceMatrixGrid matrix={defaultMatrix} onChange={handleChange} onApplyPreset={handlePreset} />);

    // 找到所有 "Deny" 按钮
    const denyButtons = screen.getAllByRole('button', { name: /deny/i });
    expect(denyButtons.length).toBeGreaterThanOrEqual(6);

    // 点击第一个能力面（knowledge_read）的 Deny 按钮
    fireEvent.click(denyButtons[0]);
    expect(handleChange).toHaveBeenCalledWith(CAPABILITY_SURFACES[0].key, 'deny');
  });

  it('triggers onApplyPreset when clicking a preset button', () => {
    const handleChange = vi.fn();
    const handlePreset = vi.fn();

    render(<CapabilitySurfaceMatrixGrid matrix={defaultMatrix} onChange={handleChange} onApplyPreset={handlePreset} />);

    const guardedBtn = screen.getByRole('button', { name: /Guarded/i });
    fireEvent.click(guardedBtn);

    expect(handlePreset).toHaveBeenCalledWith(CAPABILITY_PRESETS[0].matrix);
  });
});

describe('securityPolicyUtils capability surface helpers', () => {
  it('deriveCapabilityMatrix uses fallback default values when config is empty', () => {
    const matrix = deriveCapabilityMatrix(undefined, []);
    expect(matrix.knowledge_read).toBe('allow');
    expect(matrix.knowledge_write).toBe('ask');
    expect(matrix.web_egress).toBe('allow');
    expect(matrix.candidate_create).toBe('allow');
    expect(matrix.remote_tools).toBe('ask');
    expect(matrix.local_filesystem).toBe('ask');
  });

  it('deriveCapabilityMatrix respects explicit matrixFromConfig', () => {
    const explicit = {
      knowledge_read: 'deny' as const,
      knowledge_write: 'deny' as const,
    };
    const matrix = deriveCapabilityMatrix(explicit, []);
    expect(matrix.knowledge_read).toBe('deny');
    expect(matrix.knowledge_write).toBe('deny');
    expect(matrix.web_egress).toBe('allow'); // Fallback to default
  });

  it('syncCapabilityActionToRules replaces existing surface and tool rules cleanly', () => {
    const initialRules = [
      { permission: 'shell_exec', pattern: '*', action: 'ask' as const },
      { permission: 'wiki_query_tool', pattern: '*', action: 'allow' as const },
    ];

    const updated = syncCapabilityActionToRules(initialRules, 'knowledge_read', 'deny');
    expect(updated).toContainEqual({ permission: 'knowledge_read', pattern: '*', action: 'deny' });
    // 原有的 wiki_query_tool 应该被清理整合
    expect(updated.find((r) => r.permission === 'wiki_query_tool')).toBeUndefined();
    // 不相关的 shell_exec 应该保留
    expect(updated.find((r) => r.permission === 'shell_exec')).toBeDefined();
  });
});
