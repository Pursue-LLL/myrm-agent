/**
 * [INPUT]
 * - thinkingPermissionTypes::PermissionTier, PermissionCheckResult, isHighRiskCommand (POS: Contract & safety regex.)
 * - services/config::getConfigSyncManager (POS: Bi-directional sync with legacy securityConfig.)
 * - zustand::create (POS: Reactive state management.)
 *
 * [OUTPUT]
 * - usePermissionTierStore: hook providing reactive permission tier and smart approval gatekeeper.
 *
 * [POS]
 * Controls the 3-Tier agent authorization mode (Strict / Semi-Auto / Full-Auto),
 * enforcing safe autonomous execution while strictly intercepting destructive commands.
 */

import { create } from 'zustand';
import {
  type PermissionTier,
  type PermissionCheckResult,
  isHighRiskCommand,
} from './thinkingPermissionTypes';
import { getConfigSyncManager } from '@/services/config';

const STORAGE_KEY = 'myrm_agent_permission_tier';

const READ_ONLY_TOOLS = new Set([
  'read_file',
  'view_file',
  'list_dir',
  'search_code',
  'search_files',
  'read_url_content',
  'search_web',
  'get_file_info',
  'cat_file',
]);

const SAFE_EDIT_TOOLS = new Set([
  'write_to_file',
  'replace_file_content',
  'edit_file',
  'create_file',
  'patch_file',
]);

interface PermissionTierState {
  tier: PermissionTier;
  setTier: (tier: PermissionTier) => void;
  checkPermission: (
    toolName: string,
    params?: { command?: string; path?: string } | string,
  ) => PermissionCheckResult;
}

function getStoredTier(): PermissionTier {
  if (typeof window === 'undefined') {
    return 'strict';
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'strict' || raw === 'semi-auto' || raw === 'full-auto') {
      return raw;
    }
  } catch {
    // Ignore localStorage access failure
  }
  return 'strict';
}

function persistTier(tier: PermissionTier): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, tier);
  } catch {
    // Ignore localStorage access failure
  }
}

function syncLegacySecurityConfig(tier: PermissionTier): void {
  try {
    const syncManager = getConfigSyncManager();
    const current = syncManager.get('securityConfig');
    if (!current) {
      // Not loaded yet: writing a partial object would wipe `permissions` and the approval timeout.
      return;
    }
    syncManager.set('securityConfig', {
      ...current,
      yoloModeEnabled: tier === 'full-auto',
    });
  } catch {
    // Ignore sync failure in test or uninitialized environment
  }
}

export const usePermissionTierStore = create<PermissionTierState>((set, get) => ({
  tier: getStoredTier(),

  setTier: (tier: PermissionTier) => {
    persistTier(tier);
    syncLegacySecurityConfig(tier);
    set({ tier });
  },

  checkPermission: (
    toolName: string,
    params?: { command?: string; path?: string } | string,
  ): PermissionCheckResult => {
    const currentTier = get().tier;

    if (currentTier === 'strict') {
      return {
        approved: false,
        reason: 'strict_mode_requires_approval',
        message: '安全守护模式：所有工具执行与系统变更均需人工审批',
      };
    }

    if (currentTier === 'full-auto') {
      return {
        approved: true,
        reason: 'full_auto_yolo_allowed',
        message: '全自动无人值守模式：沙箱内零打扰自主放行',
      };
    }

    // Semi-Auto tier (Code-Safe)
    const normalizedTool = toolName.toLowerCase().trim();

    if (READ_ONLY_TOOLS.has(normalizedTool)) {
      return {
        approved: true,
        reason: 'semi_auto_code_safe_allowed',
        message: '半自动敏捷模式：只读探测操作自动放行',
      };
    }

    if (SAFE_EDIT_TOOLS.has(normalizedTool)) {
      return {
        approved: true,
        reason: 'semi_auto_code_safe_allowed',
        message: '半自动敏捷模式：文件与代码编辑自动应用',
      };
    }

    // Shell command checks
    if (normalizedTool === 'run_command' || normalizedTool === 'exec_command') {
      let commandString = '';
      if (typeof params === 'string') {
        commandString = params;
      } else if (params && typeof params === 'object' && params.command) {
        commandString = params.command;
      }

      if (isHighRiskCommand(commandString)) {
        return {
          approved: false,
          reason: 'semi_auto_high_risk_intercepted',
          message: '半自动敏捷模式：检测到高危 Shell 命令，强制阻断并等待人工审批',
        };
      }

      return {
        approved: true,
        reason: 'semi_auto_safe_command_allowed',
        message: '半自动敏捷模式：安全 Shell 命令自动执行',
      };
    }

    // For any unclassified destructive tool, require approval
    return {
      approved: false,
      reason: 'strict_mode_requires_approval',
      message: '半自动敏捷模式：未分类操作默认等待人工审批',
    };
  },
}));
