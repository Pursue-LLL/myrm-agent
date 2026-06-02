/**
 * CodeBlock 组件主题配置
 * 集中管理代码块的颜色和样式，便于全局调整
 */

export const CODE_BLOCK_THEME = {
  light: {
    /** 工具栏背景色 - 与输入框背景色一致 (--secondary) */
    toolbar: 'bg-[#f6f6f1]',
    /** 代码背景色 - 与输入框背景色一致 (--secondary) */
    background: 'bg-[#f6f6f1]',
    /** 文本颜色 */
    text: 'text-gray-700',
    /** 边框颜色 - 极浅的边框 */
    border: 'border-[#e8e8e3]',
    /** 行号颜色 */
    lineNumber: 'text-gray-400',
    /** hover 背景色 */
    hover: 'hover:bg-[#ededea]',
  },
  dark: {
    /** 工具栏背景色 - 与单行代码保持一致 */
    toolbar: 'bg-gray-800',
    /** 代码背景色 - 与单行代码保持一致 */
    background: 'bg-gray-800',
    /** 文本颜色 */
    text: 'text-gray-300',
    /** 边框颜色 - 柔和的边框 */
    border: 'border-gray-700',
    /** 行号颜色 */
    lineNumber: 'text-gray-500',
    /** hover 背景色 */
    hover: 'hover:bg-gray-700',
  },
} as const;

/** 代码块容器样式 */
export const CODE_BLOCK_CONTAINER = {
  /** 外边距（上下） */
  margin: 'my-3',
  /** 圆角 */
  rounded: 'rounded-lg',
  /** 阴影 */
  shadow: '',
} as const;

/** 代码块工具栏样式 */
export const CODE_BLOCK_TOOLBAR = {
  /** 内边距 */
  padding: 'px-3 py-1.5',
  /** 字体大小 */
  fontSize: 'text-xs',
} as const;
