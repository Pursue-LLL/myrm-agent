/**
 * Types and pre-configured questions for PreFlightAlignmentModal.
 * Adheres to AskQuestion protocol and parameter minimization principles.
 */

export interface AlignmentOption {
  id: string;
  label: string;
  description?: string;
  tag?: string;
}

export type AlignmentCategory = 'palette' | 'layout' | 'interaction' | 'audience';

export interface AlignmentQuestion {
  id: string;
  prompt: string;
  category: AlignmentCategory;
  options: AlignmentOption[];
  allowMultiple?: boolean;
}

export interface AlignmentSubmission {
  taskSummary: string;
  selectedOptions: Record<string, string[]>;
  customNotes: string;
  planBeforeExecute: boolean;
  compiledPromptConstraint: string;
}

export const DEFAULT_ALIGNMENT_QUESTIONS: AlignmentQuestion[] = [
  {
    id: 'palette',
    prompt: '视觉配色方案 (Color Palette)',
    category: 'palette',
    options: [
      {
        id: 'tech_blue',
        label: '科技深蓝 (Cyber Blue)',
        description: '高反差科技质感，深青与深蓝底色',
        tag: '推荐',
      },
      {
        id: 'minimal_light',
        label: '现代极简灰白 (Minimalist)',
        description: '克制干净，黑白灰与留白排版',
      },
      {
        id: 'academic_sage',
        label: '典雅墨绿 (Academic Sage)',
        description: '学术人文、知识沉淀温润感',
      },
      {
        id: 'warm_energetic',
        label: '活力暖橙 (Warm Amber)',
        description: '教育课件与生动演示互动',
      },
    ],
  },
  {
    id: 'layout',
    prompt: '版面交互形态 (Layout Grid)',
    category: 'layout',
    options: [
      {
        id: 'single_interactive',
        label: '单屏交互图表 (Single Screen HUD)',
        description: '全屏自适应，核心数据一屏尽览',
        tag: '高频',
      },
      {
        id: 'long_scrolling',
        label: '长流滚动长图 (Long Form Narrative)',
        description: '线性阅读叙事，图文交错递进',
      },
      {
        id: 'multi_tab',
        label: '分步向导/多Tab (Step-by-Step Tabs)',
        description: '分模块拆解，降低单次认知负荷',
      },
    ],
  },
  {
    id: 'interaction',
    prompt: '交互行为深度 (Interaction Depth)',
    category: 'interaction',
    options: [
      {
        id: 'dynamic_filtering',
        label: '动态过滤与缩放 (Filter & Zoom)',
        description: '支持点击高亮、下拉筛选与缩放',
        tag: '推荐',
      },
      {
        id: 'static_visual',
        label: '纯静态精美呈现 (Static Visual)',
        description: '只读展示，零脚本运行依赖',
      },
      {
        id: 'stateful_simulation',
        label: '状态机动态沙盘 (Stateful Sandbox)',
        description: '完整数据联动与输入模拟',
      },
    ],
  },
];
