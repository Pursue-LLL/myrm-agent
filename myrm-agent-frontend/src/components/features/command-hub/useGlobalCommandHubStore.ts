import { create } from 'zustand';
import type {
  CommandCategory,
  CommandItem,
  GlobalCommandHubState,
} from './globalCommandHubTypes';

interface GlobalCommandHubActions {
  openHub: () => void;
  closeHub: () => void;
  toggleHub: () => void;
  setSearchQuery: (query: string) => void;
  setActiveCategory: (category: CommandCategory) => void;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrevious: () => void;
  recordCommandExecution: (commandId: string) => void;
  registerCommand: (command: CommandItem) => void;
  getFilteredCommands: () => CommandItem[];
  executeSelectedCommand: () => void;
  resetState: () => void;
}

export type GlobalCommandHubStore = GlobalCommandHubState & GlobalCommandHubActions;

const DEFAULT_COMMANDS: CommandItem[] = [
  // 1. 页面导航 (Navigation)
  {
    id: 'nav-agents',
    category: 'navigation',
    title: '跳转：智能体名册矩阵',
    subtitle: '查看、编排与配置多智能体协同网络',
    shortcut: 'G A',
    iconName: 'Bot',
    keywords: ['agents', '智能体', '名册', '编排', '导航'],
    action: () => {},
  },
  {
    id: 'nav-knowledge',
    category: 'navigation',
    title: '跳转：知识库与记忆中枢',
    subtitle: '管理全局语义记忆、图谱与文档切片',
    shortcut: 'G K',
    iconName: 'BookOpen',
    keywords: ['knowledge', '知识库', '记忆', '文档', '向量'],
    action: () => {},
  },
  {
    id: 'nav-sandbox',
    category: 'navigation',
    title: '跳转：沙箱工件与Web预览',
    subtitle: '查看双视口沙箱运行态与实时页面',
    shortcut: 'G S',
    iconName: 'Laptop',
    keywords: ['sandbox', '沙箱', '工件', '预览', '端口'],
    action: () => {},
  },
  {
    id: 'nav-system',
    category: 'navigation',
    title: '跳转：系统监控与诊断',
    subtitle: '查看后台守护进程负载与健康状态',
    shortcut: 'G M',
    iconName: 'Activity',
    keywords: ['system', '系统', '监控', '负载', '设置'],
    action: () => {},
  },

  // 2. AI 快速派工 (AI Dispatch)
  {
    id: 'ai-code-review',
    category: 'ai_dispatch',
    title: '派工：代码审查与重构专家',
    subtitle: '让首席全栈架构师对当前工作区执行深度审查',
    shortcut: '⌘ 1',
    iconName: 'Sparkles',
    keywords: ['ai', '派工', 'code', 'review', '代码审查', '重构'],
    action: () => {},
  },
  {
    id: 'ai-writing-assistant',
    category: 'ai_dispatch',
    title: '派工：商务研报写作专家',
    subtitle: '整理近期会议纪要与结构化交付物',
    shortcut: '⌘ 2',
    iconName: 'FileText',
    keywords: ['ai', '派工', 'writing', '写作', '研报', '纪要'],
    action: () => {},
  },
  {
    id: 'ai-sec-audit',
    category: 'ai_dispatch',
    title: '派工：安全合规渗透测试员',
    subtitle: '扫描沙箱环境敏感密钥与潜在越权路径',
    shortcut: '⌘ 3',
    iconName: 'ShieldCheck',
    keywords: ['ai', '派工', 'security', '安全', '合规', '审计'],
    action: () => {},
  },

  // 3. 通用快捷操作 (Action)
  {
    id: 'act-new-chat',
    category: 'action',
    title: '操作：新建会话窗口',
    subtitle: '开启纯净会话上下文',
    shortcut: '⌘ N',
    iconName: 'PlusCircle',
    keywords: ['new', '新建', '会话', '聊天', 'chat'],
    action: () => {},
  },
  {
    id: 'act-clear-context',
    category: 'action',
    title: '操作：清除当前上下文记忆',
    subtitle: '瞬时清空临时会话缓存与脏工件',
    shortcut: '⌘ K ⇧ C',
    iconName: 'Trash2',
    keywords: ['clear', '清空', '上下文', '重置'],
    action: () => {},
  },
  {
    id: 'act-export-artifact',
    category: 'action',
    title: '操作：一键导出交付物产物包',
    subtitle: '将 Markdown 与代码工程打包为 Zip',
    shortcut: '⌘ E',
    iconName: 'Download',
    keywords: ['export', '导出', '交付物', '下载', 'zip'],
    action: () => {},
  },

  // 4. Git 快捷命令 (Git Operations)
  {
    id: 'git-status',
    category: 'git',
    title: 'Git：查看工作区状态 (git status)',
    subtitle: '检查未暂存修改与工作树洁净度',
    shortcut: 'G S',
    iconName: 'GitBranch',
    keywords: ['git', 'status', '状态', 'diff', '更改'],
    action: () => {},
  },
  {
    id: 'git-commit',
    category: 'git',
    title: 'Git：安全提交变更并打标签',
    subtitle: '前置跑通测试门禁并生成语义提交',
    shortcut: 'G C',
    iconName: 'GitCommit',
    keywords: ['git', 'commit', '提交', '保存'],
    action: () => {},
  },
];

const INITIAL_STATE: GlobalCommandHubState = {
  isOpen: false,
  searchQuery: '',
  activeCategory: 'all',
  selectedIndex: 0,
  recentCommandIds: ['ai-code-review', 'nav-sandbox'],
  commands: DEFAULT_COMMANDS,
};

export const useGlobalCommandHubStore = create<GlobalCommandHubStore>((set, get) => ({
  ...INITIAL_STATE,

  openHub: () => {
    set({
      isOpen: true,
      searchQuery: '',
      selectedIndex: 0,
    });
  },

  closeHub: () => {
    set({ isOpen: false });
  },

  toggleHub: () => {
    const { isOpen } = get();
    if (isOpen) {
      set({ isOpen: false });
    } else {
      set({
        isOpen: true,
        searchQuery: '',
        selectedIndex: 0,
      });
    }
  },

  setSearchQuery: (query: string) => {
    set({
      searchQuery: query,
      selectedIndex: 0,
    });
  },

  setActiveCategory: (category: CommandCategory) => {
    set({
      activeCategory: category,
      selectedIndex: 0,
    });
  },

  setSelectedIndex: (index: number) => {
    set({ selectedIndex: index });
  },

  selectNext: () => {
    const { selectedIndex } = get();
    const filtered = get().getFilteredCommands();
    if (filtered.length === 0) {
      return;
    }
    const nextIndex = (selectedIndex + 1) % filtered.length;
    set({ selectedIndex: nextIndex });
  },

  selectPrevious: () => {
    const { selectedIndex } = get();
    const filtered = get().getFilteredCommands();
    if (filtered.length === 0) {
      return;
    }
    const prevIndex = (selectedIndex - 1 + filtered.length) % filtered.length;
    set({ selectedIndex: prevIndex });
  },

  recordCommandExecution: (commandId: string) => {
    set((state) => {
      const nextRecent = [
        commandId,
        ...state.recentCommandIds.filter((id) => id !== commandId),
      ].slice(0, 5);
      return { recentCommandIds: nextRecent };
    });
  },

  registerCommand: (command: CommandItem) => {
    set((state) => ({
      commands: [
        ...state.commands.filter((c) => c.id !== command.id),
        command,
      ],
    }));
  },

  getFilteredCommands: () => {
    const { commands, searchQuery, activeCategory } = get();
    const query = searchQuery.trim().toLowerCase();

    return commands.filter((cmd) => {
      // 类别过滤
      if (activeCategory !== 'all' && cmd.category !== activeCategory) {
        return false;
      }

      // 关键词搜索
      if (!query) {
        return true;
      }

      const titleMatch = cmd.title.toLowerCase().includes(query);
      const subtitleMatch = cmd.subtitle?.toLowerCase().includes(query) ?? false;
      const keywordMatch = cmd.keywords.some((k) => k.toLowerCase().includes(query));

      return titleMatch || subtitleMatch || keywordMatch;
    });
  },

  executeSelectedCommand: () => {
    const { selectedIndex, recordCommandExecution, closeHub } = get();
    const filtered = get().getFilteredCommands();
    const target = filtered[selectedIndex];

    if (target) {
      recordCommandExecution(target.id);
      target.action();
      closeHub();
    }
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
