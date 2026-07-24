/**
 * [INPUT]
 * ./archiveRestore::* (POS: 归档恢复 SSE/进度条 payload 契约)
 * 
 * [OUTPUT]
 * RecoveryAction, ProgressItem.
 * 
 * [POS]
 * 聊天进度步骤树节点类型。
 */

import type {
  ArchiveRestoreAction,
  ArchiveRestoreBlockPayload,
  ArchiveRestoreResultPayload,
} from './archiveRestore';

export type RecoveryAction = {
  id: string;
  label: string;
  url: string;
};

export type ProgressItem = {
  step_key: string; // 步骤标识符（用于 i18n）
  parent_step_key?: string; // 父步骤标识符（用于树形结构）
  is_plan?: boolean; // 是否为计划节点
  tool_name?: string; // 工具名称（工具调用场景）
  tool_call_id?: string; // 工具调用唯一标识符（用于精准匹配并发心跳）
  reason?: string; // 执行理由（工具调用场景）
  elapsed_ms?: number; // 执行耗时（用于长耗时工具的心跳感知）
  agent_instance?: string; // Agent实例标识（用于Subagent）
  display_name?: string; // Agent自定义显示名称（优先于agent_instance）
  theme_color?: string; // Agent主题颜色（用于视觉区分）
  items?:
    | { text: string }[]
    | { query: string }[]
    | string
    | { url: string }[]
    | { skill_name: string; reason?: string }[] // 技能选择
    | {
        file_path: string;
        line_range?: string;
        action_type?: string;
        size_bytes?: string;
        diff?: string;
        diff_truncated?: boolean;
      }[] // 文件路径（用于 file_editor view）
    | { code: string }[]; // 代码内容（用于 bash_code_execute）
  status?: 'success' | 'error' | 'warning' | 'cancelled'; // 步骤执行状态（warning 用于取消）
  error?: boolean | string; // 错误标记或错误信息
  error_category?: string; // 错误分类（用于显示特殊 Badge，如 OOM, Network Blocked）
  error_hint?: string; // 诊断建议（LLM 友好或用户友好的文字提示）
  // PTC `tools.notify` 内联活动卡字段（同 category 的多次 notify 合并到一个 step）
  notify_message?: string; // 最新一次 notify 的文本
  notify_progress?: number; // 0-100 进度百分比
  notify_step_index?: number; // 当前步骤序号（>=1）
  notify_total_steps?: number; // 总步骤数（>=1）
  notify_level?: 'info' | 'warn' | 'alert'; // notify 等级（用于渲染颜色）
  notify_category?: string; // 业务分类（如 parse / render）
  recovery_actions?: RecoveryAction[]; // LLM 错误恢复操作按钮
  archive_restore_block?: ArchiveRestoreBlockPayload; // 归档恢复阻断详情，用于聊天流内恢复入口
  archive_restore_actions?: ArchiveRestoreAction[]; // 可直接发送的 typed archive restore actions
  archive_restore_result?: ArchiveRestoreResultPayload; // typed archive restore 恢复结果
  count?: number; // 计数（用于 reviewing_sources 等）
  progress_percent?: number; // 整体进度百分比（0-100）
  duration_ms?: number; // 工具执行耗时（毫秒）
  stdout?: string; // 实时终端输出流（用于 Live Terminal 组件）
  evicted_file_ref?: string; // 被 evict 的完整输出文件名（用于"查看完整输出"按钮）
};
