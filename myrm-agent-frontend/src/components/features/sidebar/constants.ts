export const DRAG_CONFIG = {
  THRESHOLD: 30,
  MIN_POSITION: 5,
  MAX_POSITION: 95,
  MAX_X: 80,
  MIN_X: -32,
  SCROLL_DELAY: 500,
  BOUNCE_DURATION: 300,
} as const;

export const STYLES = {
  sidebar: {
    base: 'fixed inset-y-0 left-0 z-50 flex flex-col transition-all duration-300 ease-in-out',
    collapsed: 'w-20',
    expanded: 'w-80',
    mobile: 'w-[90vw] max-w-[320px]',
    glass: 'backdrop-blur-xl bg-[#f3f3ee]/95 dark:bg-gray-900/80 border-r border-white/20 dark:border-white/10',
  },
  overlay: 'fixed inset-0 bg-black/50 z-40 lg:hidden',
  button: {
    base: 'transition-all duration-200 rounded-xl',
    hover: 'hover:bg-black/5 dark:hover:bg-white/5 active:scale-95',
    hoverStrong: 'hover:bg-black/10 dark:hover:bg-white/10 active:scale-95',
    touch: 'min-h-[44px] min-w-[44px]',
  },
  newChat: {
    base: 'relative overflow-hidden backdrop-blur-xl bg-gradient-to-br from-white/40 to-white/20 dark:from-white/10 dark:to-white/5 border border-white/30 dark:border-white/10 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.5),inset_0_-2px_4px_0_rgba(0,0,0,0.08),0_1px_2px_0_rgba(0,0,0,0.05)] dark:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.15),inset_0_-2px_4px_0_rgba(0,0,0,0.3),0_1px_2px_0_rgba(0,0,0,0.2)] transition-all duration-300 rounded-3xl',
    hover:
      'hover:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.6),inset_0_-2px_5px_0_rgba(0,0,0,0.1),0_2px_4px_0_rgba(0,0,0,0.08)] dark:hover:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.2),inset_0_-2px_5px_0_rgba(0,0,0,0.35),0_2px_4px_0_rgba(0,0,0,0.25)] hover:bg-gradient-to-br hover:from-white/50 hover:to-white/25 dark:hover:from-white/15 dark:hover:to-white/8 active:shadow-[inset_0_2px_4px_0_rgba(0,0,0,0.12)] dark:active:shadow-[inset_0_2px_4px_0_rgba(0,0,0,0.4)] active:scale-[0.98]',
  },
  text: {
    primary: 'text-black/90 dark:text-white/90',
    secondary: 'text-black/70 dark:text-white/70',
    muted: 'text-black/60 dark:text-white/60',
  },
} as const;
