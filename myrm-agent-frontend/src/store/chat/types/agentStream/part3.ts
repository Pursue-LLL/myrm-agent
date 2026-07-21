/**
 * [INPUT]
 * ./part1::AgentEventType, BaseAgentEvent (POS: SSE 事件类型前半段)
 * 
 * [OUTPUT]
 * FileDiff, Browser/Desktop view, ToolImageOutput 等 SSE 事件。
 * 
 * [POS]
 * SSE 事件类型末段。
 */

import { AgentEventType } from './part1';
import type { BaseAgentEvent } from './part1';
import type { FileMutationFailure } from '../sources';

export interface FileDiffStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.FILE_DIFF;
  data: {
    path: string;
    diff: string;
    is_new: boolean;
    lines_added: number;
    lines_removed: number;
    truncated: boolean;
  };
}

export interface FileMutationFailedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.FILE_MUTATION_FAILED;
  data: {
    files: FileMutationFailure[];
  };
}

export type ToolImageOutput = {
  base64?: string;
  url?: string;
  mimeType: string;
  toolName: string;
};

export interface ToolImageOutputStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_IMAGE_OUTPUT;
  tool_name: string;
  data: {
    base64?: string;
    url?: string;
    mime_type: string;
  };
}

export interface BrowserRefInfo {
  role: string;
  name: string;
  nth: number | null;
  bbox: {
    x: number;
    y: number;
    width: number;
    height: number;
    centerX: number;
    centerY: number;
    viewport_x: number;
    viewport_y: number;
    viewport_width: number;
    viewport_height: number;
  } | null;
  position: string | null;
}

export interface BrowserViewUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.BROWSER_VIEW_UPDATE;
  data: {
    screenshot_base64: string;
    mime_type: string;
    refs: Record<string, BrowserRefInfo>;
    page_url: string;
    page_title: string;
    viewport_width: number;
    viewport_height: number;
  };
}

export interface DesktopViewUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.DESKTOP_VIEW_UPDATE;
  data: {
    screenshot_base64: string;
    mime_type: string;
    refs: Record<string, BrowserRefInfo>;
    app_name: string;
    window_title: string;
    scope: string;
    needs_permission: boolean;
    viewport_width: number;
    viewport_height: number;
    screen_width?: number;
    screen_height?: number;
    dpi_scale?: number;
  };
}

export interface DesktopControlApprovalRequestStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST;
  data: {
    request_id?: string;
    reason?: string;
    operation?: string;
    app_name?: string;
    window_title?: string;
    require_app_approval?: boolean;
  };
}

export interface BrowserTakeoverRequestedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.BROWSER_TAKEOVER_REQUESTED;
  data: {
    reason?: string;
    url?: string;
    screenshot_base64?: string;
    is_managed?: boolean;
    auto_detect_completion?: boolean;
    live_assist_url?: string;
  };
}

export interface BrowserTakeoverCompletedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.BROWSER_TAKEOVER_COMPLETED;
  data?: {
    reason?: string;
  };
}

export interface PtcNotifyStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.PTC_NOTIFY;
  level?: 'info' | 'warn' | 'alert';
  message?: string;
  progress?: number;
  step_index?: number;
  total_steps?: number;
  category?: string;
  session_id?: string | null;
  trace_id?: string | null;
  data?: {
    level?: 'info' | 'warn' | 'alert';
    message?: string;
    progress?: number;
    step_index?: number;
    total_steps?: number;
    category?: string;
    session_id?: string | null;
    trace_id?: string | null;
  };
}

export interface ToolProgressStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_PROGRESS;
  tool: string;
  progress: {
    done: number;
    total: number;
    failed: number;
  };
}

export interface FissionTopologyNode {
  node_id: string;
  agent_type: string;
  objective: string;
  status: string;
  error?: string | null;
  cost_usd?: number;
}

export interface FissionTopologyUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.FISSION_TOPOLOGY;
  data: {
    fission_id: string;
    nodes: FissionTopologyNode[];
    total_cost_usd: number;
  };
}
