/**
 * In-Situ Skill Picker Zustand Store
 * 会话内就地技能拾取器、动作空间噪声联动与 postMessage 安全挂载调度器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯净状态流转，支持抽屉高度拖拽记忆与 postMessage 白名单安全过滤。
 */

import { create } from 'zustand';
import {
  InSituSkillDescriptor,
  NoiseGaugeRating,
  SkillPickerMessagePayload,
} from './inSituSkillPickerTypes';
import {
  estimateDeltaNoise,
  estimateSkillNoise,
} from './skillNoiseEstimator';

interface InSituSkillPickerState {
  skills: InSituSkillDescriptor[];
  searchQuery: string;
  categoryFilter: string;
  isDrawerOpen: boolean;
  drawerHeight: number;
  hoveredSkillId: string | null;
  allowedOrigins: string[];

  // Actions
  toggleMountSkill: (skillId: string) => void;
  setSearchQuery: (query: string) => void;
  setCategoryFilter: (category: string) => void;
  setIsDrawerOpen: (open: boolean) => void;
  setDrawerHeight: (height: number) => void;
  setHoveredSkillId: (id: string | null) => void;
  handleIncomingPostMessage: (event: MessageEvent<unknown>) => boolean;
  getFilteredSkills: () => InSituSkillDescriptor[];
  getNoiseRating: () => NoiseGaugeRating;
  getPreviewNoiseDelta: () => {
    before: NoiseGaugeRating;
    after: NoiseGaugeRating;
    deltaTokens: number;
  } | null;
  resetToDefault: () => void;
}

const DEFAULT_SKILLS: InSituSkillDescriptor[] = [
  {
    id: 'skill-python-interpreter',
    name: 'Python 沙箱执行器 (Code Interpreter)',
    description: '在安全隔离沙箱中执行 Python 代码、绘制图表与运行数值计算',
    author: 'Myrm Official',
    stars: 1240,
    category: '代码开发',
    toolCount: 3,
    estimatedTokenCost: 650,
    safetyScanStatus: 'clean',
    isMounted: true,
    version: '2.4.0',
    tags: ['Python', '数据计算', '官方'],
  },
  {
    id: 'skill-web-scraper-pro',
    name: 'Web 深度抓取与阅读 (Web Scraper Pro)',
    description: '支持自动化绕过动态 JS 渲染、提取正文与清洗 Markdown',
    author: 'Nous Community',
    stars: 890,
    category: '网页检索',
    toolCount: 4,
    estimatedTokenCost: 820,
    safetyScanStatus: 'clean',
    isMounted: true,
    version: '1.8.2',
    tags: ['爬虫', 'Markdown', '网页抓取'],
  },
  {
    id: 'skill-excel-analytics',
    name: 'Excel 与报表深度分析 (Excel Analytics)',
    description: '支持 .xlsx/.csv 复杂多表透视、公式核算与财务趋势分析',
    author: 'Hermes Contrib',
    stars: 640,
    category: '数据分析',
    toolCount: 2,
    estimatedTokenCost: 520,
    safetyScanStatus: 'clean',
    isMounted: false,
    version: '1.2.0',
    tags: ['Excel', '财务', '表格分析'],
  },
  {
    id: 'skill-pdf-extractor',
    name: 'PDF 复杂排版与公式提取 (PDF Extractor)',
    description: '高精度 OCR、多栏学术排版与 LaTeX 数学公式还原',
    author: 'Scholar Tools',
    stars: 480,
    category: '文档提取',
    toolCount: 3,
    estimatedTokenCost: 710,
    safetyScanStatus: 'clean',
    isMounted: false,
    version: '3.0.1',
    tags: ['PDF', 'OCR', '论文分析'],
  },
  {
    id: 'skill-sql-db-agent',
    name: 'SQL 智能数据库连接器 (SQL DB Connector)',
    description: '安全只读连接 PostgreSQL/MySQL，自动推导模式并执行聚合查询',
    author: 'DataOps Lab',
    stars: 920,
    category: '数据分析',
    toolCount: 5,
    estimatedTokenCost: 1100,
    safetyScanStatus: 'clean',
    isMounted: false,
    version: '2.1.0',
    tags: ['SQL', '数据库', 'Postgres'],
  },
  {
    id: 'skill-git-automation',
    name: 'Git 本地工作区自动化 (Git Automation)',
    description: '自动化分支检出、差异对比、冲突检测与规范化提交',
    author: 'DevTools Core',
    stars: 560,
    category: '代码开发',
    toolCount: 4,
    estimatedTokenCost: 880,
    safetyScanStatus: 'clean',
    isMounted: false,
    version: '1.5.0',
    tags: ['Git', '版本控制', '工作流'],
  },
];

const DEFAULT_ALLOWED_ORIGINS = [
  'https://docs.myrm.internal',
  'https://skills.myrm.internal',
  'http://localhost:3000',
  'http://localhost:8000',
];

export const useInSituSkillPickerStore = create<InSituSkillPickerState>(
  (set, get) => ({
    skills: DEFAULT_SKILLS,
    searchQuery: '',
    categoryFilter: 'all',
    isDrawerOpen: false,
    drawerHeight: 480,
    hoveredSkillId: null,
    allowedOrigins: DEFAULT_ALLOWED_ORIGINS,

    toggleMountSkill: (skillId: string) => {
      set((state) => ({
        skills: state.skills.map((skill) => {
          if (skill.id === skillId) {
            return { ...skill, isMounted: !skill.isMounted };
          }
          return skill;
        }),
      }));
    },

    setSearchQuery: (query: string) => {
      set({ searchQuery: query });
    },

    setCategoryFilter: (category: string) => {
      set({ categoryFilter: category });
    },

    setIsDrawerOpen: (open: boolean) => {
      set({ isDrawerOpen: open });
    },

    setDrawerHeight: (height: number) => {
      const clamped = Math.max(300, Math.min(760, height));
      set({ drawerHeight: clamped });
    },

    setHoveredSkillId: (id: string | null) => {
      set({ hoveredSkillId: id });
    },

    handleIncomingPostMessage: (event: MessageEvent<unknown>): boolean => {
      const { allowedOrigins, skills } = get();

      // 安全校验：Origin 白名单检查
      if (!allowedOrigins.includes(event.origin)) {
        return false;
      }

      const data = event.data as Partial<SkillPickerMessagePayload>;
      if (!data || data.type !== 'myrm-skill-pick' || !data.identifier) {
        return false;
      }

      const targetId = data.identifier;
      const targetSkill = skills.find(
        (s) => s.id === targetId || s.name === data.name
      );

      if (targetSkill) {
        // 如果存在，直接标记挂载
        get().toggleMountSkill(targetSkill.id);
        return true;
      }

      // 如果属于外部 Hub 动态注入的技能，自动注册并挂载
      const dynamicSkill: InSituSkillDescriptor = {
        id: targetId,
        name: data.name || targetId,
        description: `从技能中心 (${data.source || '外部 Hub'}) 动态装配的技能`,
        author: 'Hub Dynamic',
        stars: 1,
        category: '代码开发',
        toolCount: 2,
        estimatedTokenCost: 600,
        safetyScanStatus: 'clean',
        installCmd: data.installCmd,
        isMounted: true,
        version: '1.0.0',
        tags: ['动态挂载', 'Hub'],
      };

      set((state) => ({
        skills: [...state.skills, dynamicSkill],
      }));
      return true;
    },

    getFilteredSkills: () => {
      const { skills, searchQuery, categoryFilter } = get();
      let result = [...skills];

      if (categoryFilter && categoryFilter !== 'all') {
        result = result.filter((s) => s.category === categoryFilter);
      }

      if (searchQuery.trim().length > 0) {
        const q = searchQuery.toLowerCase().trim();
        result = result.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.description.toLowerCase().includes(q) ||
            s.tags.some((t) => t.toLowerCase().includes(q))
        );
      }

      return result;
    },

    getNoiseRating: () => {
      return estimateSkillNoise(get().skills);
    },

    getPreviewNoiseDelta: () => {
      const { skills, hoveredSkillId } = get();
      if (!hoveredSkillId) {
        return null;
      }
      const targetSkill = skills.find((s) => s.id === hoveredSkillId);
      if (!targetSkill || targetSkill.isMounted) {
        return null;
      }
      return estimateDeltaNoise(skills, targetSkill);
    },

    resetToDefault: () => {
      set({
        skills: JSON.parse(JSON.stringify(DEFAULT_SKILLS)) as InSituSkillDescriptor[],
        searchQuery: '',
        categoryFilter: 'all',
        isDrawerOpen: false,
        drawerHeight: 480,
        hoveredSkillId: null,
      });
    },
  })
);
