/**
 * SearchServiceEditDialog 组件测试
 *
 * 测试角色冲突验证逻辑
 */

import { describe, it, expect } from 'vitest';
import { isSoftSearchServiceValidationFailure } from '@/services/llm-config';
import type { SearchServiceConfigItem } from '@/store/config/types';

/**
 * 辅助函数：检查角色冲突
 * 复刻SearchServiceEditDialog中的验证逻辑
 */
function checkRoleConflict(
  searchServiceConfigs: SearchServiceConfigItem[],
  currentConfig: SearchServiceConfigItem | null,
  newRole: 'primary' | 'fallback',
): boolean {
  // 只有当配置已启用时才检查角色冲突
  if (!currentConfig?.enabled) {
    return false;
  }

  // 检查是否存在其他已启用且角色相同的配置
  const existingConfigs = searchServiceConfigs.filter((c) => c.id !== currentConfig?.id);
  return existingConfigs.some((c) => c.role === newRole && c.enabled);
}

describe('SearchServiceEditDialog 角色冲突验证', () => {
  describe('编辑已启用配置', () => {
    it('应该阻止已启用主服务改为已占用的备用角色', () => {
      // Setup: 主服务A(enabled), 备用服务B(enabled)
      const primaryConfig: SearchServiceConfigItem = {
        id: 'config-a',
        search_service: 'tavily',
        enabled: true,
        role: 'primary',
        api_key: 'key-a',
        api_base: '',
        extra_params: null,
        latency: 100,
        createdAt: Date.parse('2024-01-01'),
      };

      const fallbackConfig: SearchServiceConfigItem = {
        id: 'config-b',
        search_service: 'searxng',
        enabled: true,
        role: 'fallback',
        api_key: '',
        api_base: '',
        extra_params: null,
        latency: 200,
        createdAt: Date.parse('2024-01-02'),
      };

      const configs = [primaryConfig, fallbackConfig];

      // 验证：编辑已启用的主服务A，改为fallback角色
      const hasConflict = checkRoleConflict(configs, primaryConfig, 'fallback');

      // 期望：应该检测到冲突（因为B是已启用的fallback）
      expect(hasConflict).toBe(true);
    });

    it('应该允许已启用主服务改为未占用的备用角色', () => {
      // Setup: 只有主服务A(enabled)
      const primaryConfig: SearchServiceConfigItem = {
        id: 'config-a',
        search_service: 'tavily',
        enabled: true,
        role: 'primary',
        api_key: 'key-a',
        api_base: '',
        extra_params: null,
        latency: 100,
        createdAt: Date.parse('2024-01-01'),
      };

      const configs = [primaryConfig];

      // 验证：编辑已启用的主服务A，改为fallback角色
      const hasConflict = checkRoleConflict(configs, primaryConfig, 'fallback');

      // 期望：不应该检测到冲突（没有其他已启用的fallback）
      expect(hasConflict).toBe(false);
    });
  });

  describe('编辑未启用配置', () => {
    it('应该允许未启用配置改为任何角色（即使已占用）', () => {
      // Setup: 主服务A(enabled), 配置C(disabled)
      const primaryConfig: SearchServiceConfigItem = {
        id: 'config-a',
        search_service: 'tavily',
        enabled: true,
        role: 'primary',
        api_key: 'key-a',
        api_base: '',
        extra_params: null,
        latency: 100,
        createdAt: Date.parse('2024-01-01'),
      };

      const disabledConfig: SearchServiceConfigItem = {
        id: 'config-c',
        search_service: 'searxng',
        enabled: false,
        role: 'fallback',
        api_key: '',
        api_base: '',
        extra_params: null,
        latency: 0,
        createdAt: Date.parse('2024-01-03'),
      };

      const configs = [primaryConfig, disabledConfig];

      // Critical: 未启用配置改为primary（已被A占用）
      const hasConflict = checkRoleConflict(configs, disabledConfig, 'primary');

      // 期望：不应该检测到冲突（因为C未启用）
      expect(hasConflict).toBe(false);
    });
  });

  describe('添加新配置', () => {
    it('应该允许添加已占用角色的新配置（新配置默认未启用）', () => {
      // Setup: 主服务A(enabled)
      const primaryConfig: SearchServiceConfigItem = {
        id: 'config-a',
        search_service: 'tavily',
        enabled: true,
        role: 'primary',
        api_key: 'key-a',
        api_base: '',
        extra_params: null,
        latency: 100,
        createdAt: Date.parse('2024-01-01'),
      };

      const configs = [primaryConfig];

      // 添加新配置（config为null）
      const hasConflict = checkRoleConflict(configs, null, 'primary');

      // 期望：不触发验证（config为null，视为未启用）
      expect(hasConflict).toBe(false);
    });
  });

  describe('可视化指示', () => {
    it('应该正确计算已启用的主服务和备用服务', () => {
      // Setup: 主服务A(enabled), 备用服务B(enabled), 配置C(disabled)
      const configs: SearchServiceConfigItem[] = [
        {
          id: 'config-a',
          search_service: 'tavily',
          enabled: true,
          role: 'primary',
          api_key: 'key-a',
          api_base: '',
          extra_params: null,
          latency: 100,
          createdAt: Date.parse('2024-01-01'),
        },
        {
          id: 'config-b',
          search_service: 'searxng',
          enabled: true,
          role: 'fallback',
          api_key: '',
          api_base: '',
          extra_params: null,
          latency: 200,
          createdAt: Date.parse('2024-01-02'),
        },
        {
          id: 'config-c',
          search_service: 'perplexity',
          enabled: false,
          role: 'primary',
          api_key: 'key-c',
          api_base: '',
          extra_params: null,
          latency: 0,
          createdAt: Date.parse('2024-01-03'),
        },
      ];

      // 计算已启用配置（排除当前编辑的config-a）
      const currentConfigId = 'config-a';
      const enabled = configs.filter((c) => c.enabled && c.id !== currentConfigId);
      const primary = enabled.find((c) => c.role === 'primary');
      const fallback = enabled.find((c) => c.role === 'fallback');

      // 期望：只有B是已启用的备用服务（A被排除，C未启用）
      expect(primary).toBeUndefined();
      expect(fallback).toBeDefined();
      expect(fallback?.id).toBe('config-b');
    });
  });
});

/**
 * 辅助函数：检查配置名称是否重复
 * 复刻SearchServiceEditDialog中的验证逻辑
 */
function checkDuplicateName(
  searchServiceConfigs: SearchServiceConfigItem[],
  currentConfigId: string | undefined,
  trimmedName: string,
): boolean {
  if (!trimmedName) return false;
  return searchServiceConfigs.some(
    (c) => c.id !== currentConfigId && c.name?.trim().toLowerCase() === trimmedName.toLowerCase(),
  );
}

describe('SearchServiceEditDialog 配置名称唯一性验证', () => {
  const configs: SearchServiceConfigItem[] = [
    {
      id: 'config-a',
      name: 'My Tavily',
      search_service: 'tavily',
      enabled: true,
      role: 'primary',
      api_key: 'key-a',
      api_base: '',
      extra_params: null,
      latency: 100,
      createdAt: Date.parse('2024-01-01'),
    },
    {
      id: 'config-b',
      name: 'Backup Search',
      search_service: 'searxng',
      enabled: false,
      role: 'fallback',
      api_key: '',
      api_base: '',
      extra_params: null,
      latency: 200,
      createdAt: Date.parse('2024-01-02'),
    },
  ];

  it('应该检测到同名配置（大小写不敏感）', () => {
    expect(checkDuplicateName(configs, undefined, 'my tavily')).toBe(true);
    expect(checkDuplicateName(configs, undefined, 'MY TAVILY')).toBe(true);
  });

  it('应该允许编辑自身名称（不视为重复）', () => {
    expect(checkDuplicateName(configs, 'config-a', 'My Tavily')).toBe(false);
  });

  it('应该允许不同的名称', () => {
    expect(checkDuplicateName(configs, undefined, 'Unique Name')).toBe(false);
  });

  it('空名称不应触发重复检查', () => {
    expect(checkDuplicateName(configs, undefined, '')).toBe(false);
  });

  it('name 为 null 的配置不应参与名称匹配', () => {
    const configsWithNullName: SearchServiceConfigItem[] = [
      {
        id: 'config-c',
        name: null,
        search_service: 'perplexity',
        enabled: false,
        role: 'primary',
        api_key: 'key-c',
        api_base: '',
        extra_params: null,
        latency: 0,
        createdAt: Date.parse('2024-01-03'),
      },
    ];
    expect(checkDuplicateName(configsWithNullName, undefined, 'Perplexity')).toBe(false);
  });
});

describe('SearchServiceEditDialog 软失败识别', () => {
  it('应该把 retriable 验证失败视为可继续启用', () => {
    expect(
      isSoftSearchServiceValidationFailure({
        message: 'Search service temporarily unavailable',
        retriable: true,
      }),
    ).toBe(true);
  });

  it('应该把 quota exceeded 文案识别为软失败', () => {
    expect(
      isSoftSearchServiceValidationFailure({
        message: 'Search request failed: Search service quota exceeded — upgrade your plan',
      }),
    ).toBe(true);
  });

  it('应该拒绝硬性校验失败', () => {
    expect(
      isSoftSearchServiceValidationFailure({
        message: 'Invalid API key',
        retriable: false,
      }),
    ).toBe(false);
  });
});
