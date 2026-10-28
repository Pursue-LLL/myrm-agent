/**
 * 代码块的颜色与样式（`CODE_BLOCK_*`），以及聊天行内代码与交付物引用链接共用的单行代码芯片 `INLINE_CODE_CHIP`。
 * 芯片与代码块同底色，文字色在浅色、深色底上都不低于 4.5:1。
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
    /** hover 背景色 */
    hover: 'hover:bg-gray-700',
  },
} as const;

/** 行号颜色：用主题的次要文字色，明暗两套主题以及 diff 行底色上对比度都不低于 4.5:1 */
export const CODE_BLOCK_LINE_NUMBER = 'text-muted-foreground';

/**
 * 单行代码芯片（聊天里的行内代码、交付物引用链接）：底色与代码块一致，文字用橙色，
 * 浅色 `text-orange-700`、深色 `text-orange-400`，在各自底色上对比度都不低于 4.5:1。
 * 类名必须是完整的字面量，Tailwind 才扫得到。
 */
export const INLINE_CODE_CHIP =
  'bg-[#f6f6f1] text-orange-700 dark:bg-gray-800 dark:text-orange-400 px-1 py-0.5 rounded text-sm';

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
