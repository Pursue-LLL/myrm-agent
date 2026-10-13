'use client';

/**
 * [INPUT] '@/store/useConfigStore'::useConfigStore (POS: 配置 Store，持有用户已保存的 MCP 服务)
 * [INPUT] './catalog-types'::CatalogEntry (POS: 集成目录条目的数据结构)
 * [OUTPUT] CatalogConnectionState: 目录服务的连接状态（可连接 / 已连接 / 已停用）;
 *          resolveCatalogConnectionState: 由条目模板与已保存 MCP 服务推导连接状态的纯函数;
 *          useCatalogConnectionState: 订阅 Store，返回按条目取连接状态的函数
 * [POS] 集成目录的连接状态判定。目录卡片与引导页共用这一口径，与连接对话框的重复守卫保持一致。
 */
import { useCallback } from 'react';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry } from './catalog-types';

export type CatalogConnectionState = 'available' | 'connected' | 'disabled';

/**
 * A catalog entry is connected once the user holds an MCP service under the name its template saves
 * (the identity the connect dialog guards duplicates with); `enabled === false` is a connected service
 * the user switched off.
 */
export function resolveCatalogConnectionState(
  entry: CatalogEntry,
  mcpConfigs: readonly MCPServiceConfig[],
): CatalogConnectionState {
  const serviceName = entry.mcpConfig?.name;
  if (typeof serviceName !== 'string') {
    return 'available';
  }
  const saved = mcpConfigs.find((config) => config.name === serviceName);
  if (!saved) {
    return 'available';
  }
  return saved.enabled === false ? 'disabled' : 'connected';
}

export function useCatalogConnectionState(): (entry: CatalogEntry) => CatalogConnectionState {
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
  return useCallback((entry) => resolveCatalogConnectionState(entry, mcpConfigs), [mcpConfigs]);
}
