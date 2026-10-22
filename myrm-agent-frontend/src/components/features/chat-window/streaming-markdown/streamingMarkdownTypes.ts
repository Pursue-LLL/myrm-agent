/**
 * streamingMarkdownTypes - 高帧率增量流式渲染数据模型与状态契约
 *
 * [INPUT]
 * - 无外部运行时依赖
 *
 * [OUTPUT]
 * - MarkdownBlockType: 增量 Markdown 块类型枚举
 * - MarkdownBlock: 结构化增量块定义
 * - IncrementalParsedStream: 增量切块流式解析结果
 * - RafThrottleOptions: RAF 动态帧率节流配置参数
 * - StreamPerformanceMetrics: 渲染性能与帧率遥测指标
 *
 * [POS]
 * 增量流式 Markdown 渲染子系统的核心类型事实源。
 */

/**
 * 增量 Markdown 块类型枚举
 */
export type MarkdownBlockType =
  | 'paragraph'
  | 'code'
  | 'heading'
  | 'blockquote'
  | 'list'
  | 'table'
  | 'thematicBreak'
  | 'unknown';

/**
 * 结构化增量渲染块
 */
export interface MarkdownBlock {
  /** 块唯一稳定标识符 */
  id: string;
  /** 块语法类型 */
  type: MarkdownBlockType;
  /** 原始 Markdown 纯文本内容 */
  rawContent: string;
  /** 是否已被闭合，一旦闭合即为只读冻结快照，不再受后续 Token 追加影响 */
  isFrozen: boolean;
  /** 代码块专属语言标识（当 type 为 code 时） */
  language?: string;
  /** 标题级别 1-6（当 type 为 heading 时） */
  level?: number;
}

/**
 * 增量切块流式解析器输出
 */
export interface IncrementalParsedStream {
  /** 已闭合且冻结的稳定块列表（由 React.memo 守护，避免无效重绘） */
  frozenBlocks: MarkdownBlock[];
  /** 正在持续接收追加 Token 的末尾活跃块（仅该块在流式期间触发轻量重绘） */
  activeTailBlock: MarkdownBlock | null;
  /** 当前总块数 */
  totalBlocksCount: number;
  /** 累计全量字符数 */
  fullContentLength: number;
}

/**
 * RAF 帧率节流控制配置
 */
export interface RafThrottleOptions {
  /** 目标帧率，默认 60 fps（对应 ~16.6ms 刷新窗口） */
  targetFps?: number;
  /** 单帧最大提取 Token 字符批量，防止超大 chunk 阻塞单帧，默认 1500 */
  maxBatchCharsPerFrame?: number;
  /** 自适应文本降级阈值（tokens/s），超过该速度时临时关闭重型代码高亮以保证主线程丝滑响应，默认 120 */
  highThroughputThresholdTokensPerSec?: number;
}

/**
 * 流式渲染运行期性能遥测指标
 */
export interface StreamPerformanceMetrics {
  /** 当前测量帧率 (FPS) */
  currentFps: number;
  /** 估算瞬时生成速率 (Tokens/s) */
  tokensPerSecond: number;
  /** 累计丢帧次数 */
  droppedFrames: number;
  /** 是否已激活自适应极速轻量排版降级模式 */
  isDegradedMode: boolean;
}
