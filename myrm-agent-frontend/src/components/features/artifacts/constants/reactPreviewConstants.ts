/**
 * React预览配置常量
 */

/** 预装依赖版本（与 Claude Artifacts 对齐） */
export const PRESET_DEPENDENCIES: Record<string, string> = {
  // UI 相关
  'lucide-react': 'latest',
  clsx: 'latest',
  'class-variance-authority': 'latest',
  'tailwind-merge': 'latest',
  // 图表
  recharts: '^2.12.0',
  // 动画
  'framer-motion': '^11.0.0',
  // 日期处理
  'date-fns': '^3.0.0',
  // 工具库
  lodash: '^4.17.21',
  // 状态管理（轻量）
  zustand: '^4.5.0',
  // 表单
  'react-hook-form': '^7.50.0',
};

/** 可选依赖（根据代码自动检测） */
export const OPTIONAL_DEPENDENCIES: Record<string, string> = {
  // Radix UI 组件（覆盖 Shadcn UI 全套原语）
  '@radix-ui/react-accordion': 'latest',
  '@radix-ui/react-alert-dialog': 'latest',
  '@radix-ui/react-avatar': 'latest',
  '@radix-ui/react-checkbox': 'latest',
  '@radix-ui/react-collapsible': 'latest',
  '@radix-ui/react-context-menu': 'latest',
  '@radix-ui/react-dialog': 'latest',
  '@radix-ui/react-dropdown-menu': 'latest',
  '@radix-ui/react-hover-card': 'latest',
  '@radix-ui/react-label': 'latest',
  '@radix-ui/react-menubar': 'latest',
  '@radix-ui/react-navigation-menu': 'latest',
  '@radix-ui/react-popover': 'latest',
  '@radix-ui/react-progress': 'latest',
  '@radix-ui/react-radio-group': 'latest',
  '@radix-ui/react-scroll-area': 'latest',
  '@radix-ui/react-select': 'latest',
  '@radix-ui/react-separator': 'latest',
  '@radix-ui/react-slider': 'latest',
  '@radix-ui/react-slot': 'latest',
  '@radix-ui/react-switch': 'latest',
  '@radix-ui/react-tabs': 'latest',
  '@radix-ui/react-toast': 'latest',
  '@radix-ui/react-toggle': 'latest',
  '@radix-ui/react-toggle-group': 'latest',
  '@radix-ui/react-tooltip': 'latest',
  // 其他常用库
  axios: 'latest',
  uuid: 'latest',
  nanoid: 'latest',
};

/** Tailwind CSS 基础样式 */
export const TAILWIND_CSS = `
@tailwind base;
@tailwind components;
@tailwind utilities;

/* 额外的实用样式 */
.animate-in {
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 滚动条美化 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(155, 155, 155, 0.5);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(155, 155, 155, 0.7);
}
`;

/** cn() 工具函数（Shadcn UI 标准模式：clsx + tailwind-merge） */
export const CN_UTILS_CODE = `import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
export function cn(...inputs) { return twMerge(clsx(inputs)); }
`;

/** Tailwind 配置 */
export const TAILWIND_CONFIG = `
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./**/*.{js,jsx,ts,tsx}"],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        border: "hsl(214.3 31.8% 91.4%)",
        input: "hsl(214.3 31.8% 91.4%)",
        ring: "hsl(222.2 84% 4.9%)",
        background: "hsl(0 0% 100%)",
        foreground: "hsl(222.2 84% 4.9%)",
        primary: {
          DEFAULT: "hsl(222.2 47.4% 11.2%)",
          foreground: "hsl(210 40% 98%)",
        },
        secondary: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        destructive: {
          DEFAULT: "hsl(0 84.2% 60.2%)",
          foreground: "hsl(210 40% 98%)",
        },
        muted: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(215.4 16.3% 46.9%)",
        },
        accent: {
          DEFAULT: "hsl(210 40% 96.1%)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        card: {
          DEFAULT: "hsl(0 0% 100%)",
          foreground: "hsl(222.2 84% 4.9%)",
        },
      },
      borderRadius: {
        lg: "0.5rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
    },
  },
  plugins: [],
}
`;
