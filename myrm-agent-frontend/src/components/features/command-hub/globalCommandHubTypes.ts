/**
 * 全局 ⌘K 全能命令中枢、四类动作混排模糊搜索与跨模块极速分发契约定义
 */

export type CommandCategory = 'all' | 'navigation' | 'ai_dispatch' | 'action' | 'git';

export interface CommandItem {
  id: string;
  category: Exclude<CommandCategory, 'all'>;
  title: string;
  subtitle?: string;
  shortcut?: string;
  iconName: string;
  keywords: string[];
  action: () => void;
}

export interface GlobalCommandHubState {
  isOpen: boolean;
  searchQuery: string;
  activeCategory: CommandCategory;
  selectedIndex: number;
  recentCommandIds: string[];
  commands: CommandItem[];
}
