/**
 * 智能体画廊常量配置
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - lucide-react: 图标组件
 * - hugeicons-react: 额外图标组件
 * - @/types/presetAgent::PresetAgentCategory (POS: 预置智能体类型定义)
 *
 * [OUTPUT]
 * - iconMap: 图标名称 → 图标组件映射
 * - categoryColors: 智能体类别 → 颜色主题映射
 * - CLI_WORKING_DIRECTORY_STORAGE_KEY: CLI 工作路径 localStorage key
 * - CLI_RECENT_PROJECTS_STORAGE_KEY: 最近项目 localStorage key
 * - MAX_RECENT_PROJECTS: 最大最近项目数量
 * - customAgentGradients: 自定义智能体渐变色方案
 *
 * [POS]
 * 智能体画廊的常量配置。集中管理图标映射、颜色主题、
 * localStorage key 等配置，避免魔法字符串散落在代码中。
 * 被 PresetAgentCard、CLIWorkingDirectory 等组件引用。
 */

import {
  Terminal,
  Braces,
  MessageCircle,
  FileText,
  Link,
  FileSearch,
  FolderPlus,
  SearchCode,
  Bug,
  User,
} from 'lucide-react';
import { AiNetworkIcon } from 'hugeicons-react';
import type { PresetAgentCategory } from '@/types/presetAgent';

/** 图标映射 */
export const iconMap: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  Terminal,
  AiNetworkIcon,
  Braces,
  MessageCircle,
  FileText,
  Link,
  FileSearch,
  FolderPlus,
  SearchCode,
  Bug,
  User,
};

/** 类别颜色映射 */
export const categoryColors: Record<PresetAgentCategory, { bg: string; text: string; border: string; iconBg: string }> =
  {
    general: {
      bg: 'bg-amber-500/10',
      text: 'text-amber-600 dark:text-amber-400',
      border: 'border-amber-500/20',
      iconBg: 'bg-gradient-to-br from-amber-400 to-orange-500',
    },
    cli_visual: {
      bg: 'bg-violet-500/10',
      text: 'text-violet-600 dark:text-violet-400',
      border: 'border-violet-500/20',
      iconBg: 'bg-gradient-to-br from-violet-400 to-purple-500',
    },
  };

/** localStorage key for CLI working directory */
export const CLI_WORKING_DIRECTORY_STORAGE_KEY = 'cli-visual-agent-working-directory';

/** localStorage key for recent projects */
export const CLI_RECENT_PROJECTS_STORAGE_KEY = 'cli-visual-recent-projects';

/** Maximum number of recent projects to store */
export const MAX_RECENT_PROJECTS = 5;

/** 自定义智能体头像渐变色方案 */
export const customAgentGradients = [
  'from-blue-400 to-cyan-500',
  'from-violet-400 to-purple-500',
  'from-emerald-400 to-teal-500',
  'from-orange-400 to-amber-500',
  'from-pink-400 to-rose-500',
  'from-indigo-400 to-blue-500',
];
