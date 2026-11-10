/**
 * [OUTPUT] 审批对话框与超时观察者测试的共享底座（供 mock 工厂动态导入，不引入 store 与组件）：
 *          sonner 与恢复流的替身、审批请求构造器。
 */
import { vi } from 'vitest';

import type { ToolApprovalRequest } from '@/store/chat/types';

const hoisted = vi.hoisted(() => ({
  resume: vi.fn(),
  toast: { warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}));
export { hoisted as kit };

export function sonnerMock() {
  return { toast: hoisted.toast };
}

/** 保留真实的 `buildApprovalDecision`，只替换会发请求的 `resumeApprovalStream`。 */
export function resumeMock<T extends object>(actual: T) {
  return { ...actual, resumeApprovalStream: (...args: unknown[]) => hoisted.resume(...args) };
}

/** 默认是一条还有 5 分钟才到期的 shell 审批；调用时按当前（可能是假）时钟取时间。 */
export function approvalRequest(overrides: Partial<ToolApprovalRequest> = {}): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'bash_code_execute_tool',
    toolInput: { command: 'ls' },
    reason: '',
    timeoutSeconds: 300,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}
