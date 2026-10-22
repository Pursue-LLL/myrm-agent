/**
 * 自然阻尼物理弹簧曲线库与微交互设计规范核心 Token（SSOT）
 */

export interface SpringCurveDefinition {
  name: string;
  bezier: string;
  dampingRatio: number;
  description: string;
}

export const SPRING_CURVES: Record<string, SpringCurveDefinition> = {
  enter: {
    name: 'Natural Enter',
    bezier: 'cubic-bezier(0.16, 1, 0.3, 1)',
    dampingRatio: 0.85,
    description: '迅捷轻快自然展开，用于弹窗、抽屉与浮层出现',
  },
  exit: {
    name: 'Snappy Exit',
    bezier: 'cubic-bezier(0.7, 0, 0.84, 0)',
    dampingRatio: 0.95,
    description: '干净利落不拖泥带水，用于元素销毁与退出',
  },
  spring: {
    name: 'Bouncy Spring',
    bezier: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    dampingRatio: 0.65,
    description: '活泼微妙的 Q 弹反馈，用于点赞、收藏与微交互',
  },
  smooth: {
    name: 'Premium Smooth',
    bezier: 'cubic-bezier(0.4, 0, 0.2, 1)',
    dampingRatio: 1.0,
    description: '丝滑典雅无过冲，用于高级卡片展开与平滑过渡',
  },
  snappy: {
    name: 'Snappy Micro',
    bezier: 'cubic-bezier(0.25, 1, 0.5, 1)',
    dampingRatio: 0.9,
    description: '灵动轻快，用于按钮按下与标签页切换',
  },
};

export type MotionPersonality = 'playful' | 'premium' | 'corporate' | 'energetic';

export interface MotionPersonalityConfig {
  personality: MotionPersonality;
  displayName: string;
  durationMs: number;
  overshootPercent: number;
  timingFunction: string;
  activeScale: number;
  description: string;
}

export const MOTION_PERSONALITIES: Record<MotionPersonality, MotionPersonalityConfig> = {
  playful: {
    personality: 'playful',
    displayName: '活泼亲和 (Playful)',
    durationMs: 220,
    overshootPercent: 15,
    timingFunction: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    activeScale: 0.96,
    description: '150–300ms 伴随 10–20% 过冲，充满弹性趣味与陪伴感',
  },
  premium: {
    personality: 'premium',
    displayName: '高端沉稳 (Premium)',
    durationMs: 450,
    overshootPercent: 0,
    timingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)',
    activeScale: 0.985,
    description: '350–600ms 零过冲，丝滑、从容、顶级设计品质',
  },
  corporate: {
    personality: 'corporate',
    displayName: '严谨商务 (Corporate)',
    durationMs: 250,
    overshootPercent: 2,
    timingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
    activeScale: 0.98,
    description: '200–400ms 0–3% 极轻微过冲，清晰稳重，效率至上',
  },
  energetic: {
    personality: 'energetic',
    displayName: '极速敏捷 (Energetic)',
    durationMs: 160,
    overshootPercent: 25,
    timingFunction: 'cubic-bezier(0.16, 1.4, 0.3, 1)',
    activeScale: 0.95,
    description: '100–250ms 15–30% 快速回弹，响应瞬发极客流',
  },
};

export type MotionStackLane = 'css_spring' | 'motion_dev' | 'gsap' | 'rive' | 'lottie';

export interface MotionStackLaneGuide {
  lane: MotionStackLane;
  name: string;
  recommendation: string;
  bundleWeight: string;
  guardrails: string[];
}

export const MOTION_STACK_LANES: Record<MotionStackLane, MotionStackLaneGuide> = {
  css_spring: {
    lane: 'css_spring',
    name: '纯 CSS 物理弹簧 (Zero-JS CSS Spring)',
    recommendation: '聊天会话流内联轻量 HTML Widget、基础微交互与按钮卡片',
    bundleWeight: '0 KB (纯原生 CSS 变量)',
    guardrails: [
      '严禁在内联小卡片引入重型外部动效 JS 库',
      '强制支持 prefers-reduced-motion 语义保留降级',
      '仅对 transform、opacity、filter 施加动画',
    ],
  },
  motion_dev: {
    lane: 'motion_dev',
    name: 'Motion.dev (React 状态与布局动效)',
    recommendation: 'React Web UI 组件复杂状态迁移、FLIP layoutId 共享布局过渡',
    bundleWeight: '~18 KB',
    guardrails: [
      '组件卸载时确保 AnimatePresence 退出动效干净',
      '列表重排强制绑定稳定 key 避免布局跳变',
    ],
  },
  gsap: {
    lane: 'gsap',
    name: 'GSAP 3 (时间轴编排与字符叙事)',
    recommendation: '复杂多轨时间轴、滚动触发叙事 (ScrollTrigger) 与字符级拆字 (SplitText)',
    bundleWeight: '~25 KB (现全部官方免费商业可用)',
    guardrails: [
      '在 React 中强制使用 useGSAP + scope 自动清理上下文防内存泄漏',
      '严禁在常规简单按钮中使用 GSAP 时间轴',
    ],
  },
  rive: {
    lane: 'rive',
    name: 'Rive 状态机驱动角色 (@rive-app/canvas)',
    recommendation: '复杂可交互 2D 骨骼角色、动态矢量吉祥物与实时状态徽章',
    bundleWeight: 'WASM Runtime',
    guardrails: [
      'Trap 28 铁律: .riv 为二进制资产，严禁代码凭空编写 .riv 文件',
      '必须仅挂载外部只读 .riv 并通过状态机 Inputs 触发',
    ],
  },
  lottie: {
    lane: 'lottie',
    name: 'Lottie 矢量动画 (dotLottie)',
    recommendation: '循环矢量图表、成功打勾动画、轻量微动图标',
    bundleWeight: '~15 KB',
    guardrails: [
      'Trap 27: 多维变换施加在挂载容器而非内部图层以防渲染空白',
      '禁止将大尺寸全屏视频伪装为 Lottie 渲染',
    ],
  },
};

/**
 * 4px/8px 空间网格系统标准化节奏
 */
export const SPATIAL_GRID_SPACINGS = [
  { px: 2, tailwind: '0.5' },
  { px: 4, tailwind: '1' },
  { px: 8, tailwind: '2' },
  { px: 12, tailwind: '3' },
  { px: 16, tailwind: '4' },
  { px: 24, tailwind: '6' },
  { px: 32, tailwind: '8' },
  { px: 48, tailwind: '12' },
  { px: 64, tailwind: '16' },
] as const;

/**
 * GPU 合成属性静态安全检查
 */
export function validateGpuMotionSafety(cssProperties: string[]): {
  isSafe: boolean;
  violations: string[];
} {
  const violations: string[] = [];
  const layoutTriggeringProps = ['width', 'height', 'top', 'left', 'right', 'bottom', 'margin', 'padding'];

  for (const prop of cssProperties) {
    const normalized = prop.trim().toLowerCase();
    if (layoutTriggeringProps.includes(normalized)) {
      violations.push(`属性 '${normalized}' 会引发浏览器重排重绘 (Layout Thrashing)，应替换为 transform / opacity`);
    }
  }

  return {
    isSafe: violations.length === 0,
    violations,
  };
}
