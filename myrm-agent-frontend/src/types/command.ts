/**
 * 快捷指令类型定义
 *
 * - 行为 (Actions): 系统内置功能（含参数提示、别名搜索）
 * - 命令 (Commands): 用户自定义模板
 */

/**
 * 快捷指令项类型
 */
export type SlashItemType = 'action' | 'command';

/**
 * 行为定义（系统内置）
 */
export interface SlashAction {
  /** 唯一标识 */
  id: string;

  /** 行为名称（触发词） */
  name: string;

  /** 行为描述 */
  description: string;

  /** 图标 */
  icon?: string;

  /** 参数用法提示，显示在命令面板中（如 "[on|off|<seconds>]"） */
  argsHint?: string;

  /** 命令别名，用于搜索匹配（如 ["reset", "clear"]） */
  aliases?: string[];

  /** 类型标识 */
  type: 'action';

  /** 执行函数 */
  execute: (inputValue: string) => Promise<ActionResult> | ActionResult;
}

/**
 * 行为执行结果
 */
export interface ActionResult {
  /** 是否成功 */
  success: boolean;
  /** 错误信息（失败时） */
  error?: string;
  /** 新的输入值（可选） */
  newInputValue?: string;
}

/**
 * 命令定义（用户自定义）
 */
export interface SlashCommand {
  /** 唯一标识 */
  id: string;

  /** 命令名称（触发词） */
  name: string;

  /** 类型标识 */
  type: 'command';

  /** 指令文本（在光标位置追加的内容） */
  template: string;

  /** 创建时间 */
  createdAt: string;

  /** 更新时间 */
  updatedAt: string;
}

/**
 * 快捷指令项（行为或命令）
 */
export type SlashItem = SlashAction | SlashCommand;
