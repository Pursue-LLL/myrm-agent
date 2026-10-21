/**
 * [INPUT]
 * - None (纯契约与数据模型定义)
 *
 * [OUTPUT]
 * - TurnFileOperation: 文件变更操作语义类型
 * - TurnFileChange: 单文件变更实体
 * - TurnRevertState: 单轮回滚状态机数据结构
 * - InlineReviewComment: 行内批注实体
 * - SurgicalFixPayload: 定向修复 Payload 契约
 *
 * [POS]
 * 会话流文件修改一键撤销与 Diff 行内划词批注修复套件的核心类型契约定义。
 */

export type TurnFileOperation = 'create' | 'update' | 'delete';

export interface TurnFileChange {
  path: string;
  operation: TurnFileOperation;
  has_original: boolean;
  timestamp: number;
  revertible?: boolean;
  skip_reason?: string | null;
  additions?: number;
  deletions?: number;
}

export type TurnRevertStatus = 'idle' | 'loading' | 'success' | 'error';

export interface TurnRevertState {
  status: TurnRevertStatus;
  revertedFiles: string[];
  warnings: string[];
  skippedFiles: string[];
  errorMessage?: string;
}

export interface InlineReviewComment {
  id: string;
  filePath: string;
  lineNumber: number;
  lineType: 'addition' | 'deletion' | 'context';
  selectedCode: string;
  comment: string;
  createdAt: number;
}

export interface SurgicalFixPayload {
  filePath: string;
  lineNumber: number;
  selectedCode: string;
  comment: string;
  sessionId: string;
  messageId?: string;
}
