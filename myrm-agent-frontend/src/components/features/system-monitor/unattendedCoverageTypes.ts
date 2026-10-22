/**
 * 无人值守与多渠道运行事件日志覆盖状态前端类型定义
 */

export type EntrypointType =
  | 'cron'
  | 'channel'
  | 'goal'
  | 'voice'
  | 'voice_realtime'
  | 'web_chat';

export interface EntrypointCoverageSpec {
  entrypoint: EntrypointType;
  is_injected: boolean;
  strategy_desc: string;
  sample_session_id: string;
  is_safe: boolean;
}

export interface ShardSummary {
  prefix: string;
  file_count: number;
  total_bytes: number;
}

export interface CoverageSummaryResponse {
  event_log_dir: string | null;
  max_line_bytes: number | null;
  is_directory_configured: boolean;
  entrypoints: EntrypointCoverageSpec[];
  anti_growth_protection: boolean;
  shards: ShardSummary[];
}

export interface ValidateSessionIdRequest {
  entrypoint: 'cron' | 'channel' | 'goal' | 'voice' | 'voice_realtime';
  raw_identifier: string;
}

export interface ValidateSessionIdResponse {
  entrypoint: string;
  resolved_session_id: string;
  is_safe: boolean;
  is_daily_sharded: boolean;
}
