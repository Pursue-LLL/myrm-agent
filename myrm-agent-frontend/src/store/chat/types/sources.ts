/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

// 外部引用来源类型
export type SourceType = 'web_search' | 'web_fetch' | 'mcp' | 'conversation_history';

// MCP 调用记录
export interface MCPCallRecord {
  tool_name: string; // 工具名称
  result_preview: string; // 返回结果摘要（前500字符）
}

// 外部引用来源数据
export interface Source {
  index: number; // 引用编号（从1开始）
  type: SourceType; // 来源类型
  source_key?: string; // 稳定去重键
  // web_search 和 web_fetch 共有字段
  url?: string; // URL
  title?: string; // 页面标题
  snippet?: string; // 摘要（仅 web_search）
  summary?: string; // 长摘要（会话历史等结构化来源）
  score?: number; // 相关度
  // mcp 技能字段
  skill_name?: string; // 技能名称
  calls?: MCPCallRecord[]; // MCP 调用记录列表
  // knowledge base fields
  kb_name?: string;
  filename?: string;
  section?: string;
  // conversation_history 字段
  conversation_id?: string;
  message_id?: string;
  agent_id?: string;
  surface?: string;
  fork_parent_id?: string;
  lineage?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CitedMemoryReference {
  id: string;
  memoryType?: string;
  content?: string;
  score?: number;
  createdAt?: string;
  primaryNamespace?: string;
  namespaces?: string[];
  sourceChatId?: string;
  sourceMessageId?: string;
}

export interface FileMutationFailure {
  path: string;
  tool: string;
  error_preview: string;
}

