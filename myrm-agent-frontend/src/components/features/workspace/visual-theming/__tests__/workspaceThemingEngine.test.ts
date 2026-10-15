import { describe, it, expect } from 'vitest';
import {
  getColorClasses,
  getModeAdaptiveSuggestions,
  validateWorkspaceTheme,
  formatWorkspaceBreadcrumb,
} from '../workspaceThemingEngine';
import { WorkspaceItem } from '../workspaceThemingTypes';

describe('workspaceThemingEngine', () => {
  describe('getColorClasses', () => {
    it('returns violet styling classes for violet color', () => {
      const res = getColorClasses('violet');
      expect(res.textClass).toContain('violet');
      expect(res.bgClass).toContain('violet');
      expect(res.borderClass).toContain('violet');
      expect(res.glowClass).toContain('139,92,246');
    });

    it('returns amber styling classes for amber color', () => {
      const res = getColorClasses('amber');
      expect(res.textClass).toContain('amber');
      expect(res.bgClass).toContain('amber');
      expect(res.borderClass).toContain('amber');
    });

    it('returns emerald styling classes for emerald color', () => {
      const res = getColorClasses('emerald');
      expect(res.textClass).toContain('emerald');
    });

    it('falls back to slate styling for slate color', () => {
      const res = getColorClasses('slate');
      expect(res.textClass).toContain('slate');
    });
  });

  describe('getModeAdaptiveSuggestions', () => {
    it('returns coding-centric suggestions when mode is coding', () => {
      const suggestions = getModeAdaptiveSuggestions('coding');
      expect(suggestions.length).toBe(3);
      expect(suggestions[0]?.category).toBe('代码工程');
      expect(suggestions[1]?.category).toBe('质量门禁');
      expect(suggestions[2]?.category).toBe('性能调优');
      expect(suggestions.every((s) => s.mode === 'coding')).toBe(true);
    });

    it('returns work/business-centric suggestions when mode is work', () => {
      const suggestions = getModeAdaptiveSuggestions('work');
      expect(suggestions.length).toBe(3);
      expect(suggestions[0]?.category).toBe('商务办公');
      expect(suggestions[1]?.category).toBe('团队协同');
      expect(suggestions[2]?.category).toBe('法务风控');
      expect(suggestions.every((s) => s.mode === 'work')).toBe(true);
    });
  });

  describe('validateWorkspaceTheme', () => {
    it('fills default violet and code if theme is undefined or partial', () => {
      expect(validateWorkspaceTheme()).toEqual({
        color: 'violet',
        icon: 'code',
        customLabel: undefined,
      });

      expect(
        validateWorkspaceTheme({ color: 'blue', customLabel: ' 架构设计 ' }),
      ).toEqual({
        color: 'blue',
        icon: 'code',
        customLabel: '架构设计',
      });
    });
  });

  describe('formatWorkspaceBreadcrumb', () => {
    it('formats breadcrumb text with current mode label', () => {
      const mockWorkspace: WorkspaceItem = {
        id: 'ws-1',
        name: '核心引擎项目',
        path: '/projects/core',
        defaultMode: 'coding',
        theme: { color: 'violet', icon: 'code' },
        updatedAt: Date.now(),
      };

      expect(formatWorkspaceBreadcrumb(mockWorkspace, 'coding')).toBe(
        '核心引擎项目 · 编程模式',
      );
      expect(formatWorkspaceBreadcrumb(mockWorkspace, 'work')).toBe(
        '核心引擎项目 · 通用办公模式',
      );
    });
  });
});
