/**
 * 工件系统配置常量
 * 集中管理 Magic Numbers，便于维护
 */

// ==================== 缓存配置 ====================

/** 最大缓存条目数（基于内存优化） */
export const ARTIFACT_CACHE_MAX_SIZE = 30;

/** 缓存有效期（毫秒）- 10 分钟（延长以减少重复加载） */
export const ARTIFACT_CACHE_TTL = 10 * 60 * 1000;

/** 缓存清理间隔（毫秒）- 每 2 分钟自动清理过期缓存 */
export const CACHE_CLEANUP_INTERVAL = 2 * 60 * 1000;

/** 大文件阈值（字节）- 超过此大小的文件会有特殊处理 */
export const LARGE_FILE_THRESHOLD = 1024 * 1024; // 1MB

/** 启用缓存压缩（对大文件进行压缩存储） */
export const ENABLE_CACHE_COMPRESSION = true;

// ==================== 虚拟滚动配置 ====================

/** 虚拟滚动阈值：超过此行数启用虚拟滚动（优化为 300 行） */
export const VIRTUAL_SCROLL_THRESHOLD = 300;

/** 每行预估高度（像素） */
export const ESTIMATED_LINE_HEIGHT = 20;

/** 虚拟滚动预渲染行数（增加以改善滚动体验） */
export const VIRTUAL_SCROLL_OVERSCAN = 30;

/** 虚拟滚动节流延迟（毫秒） */
export const VIRTUAL_SCROLL_THROTTLE = 16; // 约60fps

// ==================== Portal 面板配置 ====================

/** Portal 面板最小宽度（像素） */
export const PORTAL_MIN_WIDTH = 320;

/** Portal 面板最大宽度（像素） */
export const PORTAL_MAX_WIDTH = 800;

/** Portal 面板默认宽度（像素） */
export const PORTAL_DEFAULT_WIDTH = 600;

/** 移动端断点（像素） */
export const MOBILE_BREAKPOINT = 768;

// ==================== 手势配置 ====================

/** 触摸滑动关闭阈值（像素） */
export const SWIPE_CLOSE_THRESHOLD = 100;

/** 触摸滑动最大偏移（像素） */
export const SWIPE_MAX_OFFSET = 200;

// ==================== 预加载配置 ====================

/** 鼠标悬停预加载延迟（毫秒） */
export const PRELOAD_DELAY = 200;

/** 图片懒加载提前距离（像素） */
export const IMAGE_LAZY_LOAD_MARGIN = 100;

/** 启用智能预加载（基于用户行为预测） */
export const ENABLE_SMART_PRELOAD = true;

/** 预加载队列最大长度 */
export const PRELOAD_QUEUE_MAX_SIZE = 3;

// ==================== 版本历史配置 ====================

/** 每个 Artifact 最大保留版本数 */
export const MAX_VERSIONS_PER_ARTIFACT = 50;

// ==================== 标签页管理配置 ====================

/** 最大同时打开的标签页数量（防止内存泄漏） */
export const MAX_OPEN_TABS = 8;

/** 标签页自动关闭策略：'oldest' | 'least-used' */
export const TAB_CLOSE_STRATEGY = 'oldest' as const;

/** 标签页空闲超时（毫秒）- 超过此时间未访问的标签页优先关闭 */
export const TAB_IDLE_TIMEOUT = 30 * 60 * 1000; // 30 分钟

// ==================== 性能监控配置 ====================

/** 启用性能监控 */
export const ENABLE_PERFORMANCE_MONITORING = true;

/** 性能警告阈值（毫秒） */
export const PERFORMANCE_WARNING_THRESHOLD = {
  /** 内容加载时间 */
  contentLoad: 3000,
  /** 渲染时间 */
  render: 100,
  /** 交互响应时间 */
  interaction: 100,
} as const;
