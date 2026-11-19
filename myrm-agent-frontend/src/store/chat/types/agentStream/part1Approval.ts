/**
 * [INPUT]
 * ./part1::AgentEventType, BaseAgentEvent (POS: SSE 事件类型表与事件基类)
 *
 * [OUTPUT]
 * ToolApprovalRequestStreamEvent, ApprovalRequiredStreamEvent, ClarificationRequiredStreamEvent: 让运行停下来等人答复的 SSE 事件（工具审批、审批提示、澄清提问）
 *
 * [POS]
 * 「等人答复」事件的类型定义；由 types/index.ts 再导出，并由 union.ts 纳入 AgentStreamEvent 联合。
 */

import { AgentEventType } from './part1';
import type { BaseAgentEvent } from './part1';

export interface ToolApprovalRequestStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_APPROVAL_REQUEST;
  /** LangGraph interrupt the card answers; the same interrupt is announced again while it stays pending. */
  interruptId?: string;
  data: {
    // Standard LangChain HITL structure
    actionRequests: Array<{
      action: string;
      args: Record<string, unknown>;
      description: string;
      domains?: string[];
      ptc_annotations?: Record<string, boolean>;
    }>;
    reviewConfigs: Array<{
      allowedDecisions: Array<'approve' | 'reject' | 'edit'>;
      domainApproval?: boolean;
      smartDenied?: boolean;
      hideAllowAlways?: boolean;
      heldForPerson?: boolean;
      isSpend?: boolean;
      spendAmount?: number;
      spendCurrency?: string;
      actionDigest?: string;
    }>;
    // Extensions (custom fields)
    extensions: {
      timeout: {
        seconds: number;
        expiresAt: number;
        behavior: 'deny' | 'allow';
      };
      approval: {
        requestId: string;
        sessionKey: string;
        permissionType: string;
        allowAlways: boolean;
      };
      displayMode: 'approval' | 'handover';
    };
  };
}

export interface ApprovalRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.APPROVAL_REQUIRED;
  interruptId?: string;
  data: {
    type: string;
    message?: string;
    [key: string]: unknown;
  };
}

export interface ClarificationRequiredWireData {
  type: 'ask_question';
  form: unknown;
}

export interface ClarificationRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CLARIFICATION_REQUIRED;
  /** LangGraph interrupt the card answers: the answer is addressed to it, so it can never settle a later pause. */
  interruptId?: string;
  data: ClarificationRequiredWireData;
}
