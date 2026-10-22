/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - CanvasSandboxPolicy, CanvasEgressRequest, CanvasPermissionStatus, CanvasSecurityAuditEvent, CanvasViewerProps
 *
 * [POS]
 * Domain types for Canvas safe sandboxing and interactive script gating (Item 44 P0).
 * Strictly under 80 lines. Zero `any`.
 */

export type CanvasSandboxPolicy = 'allow-scripts allow-forms';

export type CanvasPermissionStatus = 'pending' | 'allowed' | 'denied';

export interface CanvasEgressRequest {
  id: string;
  url: string;
  method: string;
  domain: string;
  timestamp: number;
  status: CanvasPermissionStatus;
}

export type CanvasAuditEventType =
  | 'blocked-parent-access'
  | 'egress-requested'
  | 'egress-allowed'
  | 'egress-denied'
  | 'sandbox-initialized';

export interface CanvasSecurityAuditEvent {
  id: string;
  type: CanvasAuditEventType;
  detail: string;
  timestamp: number;
  domain?: string;
}

export interface CanvasViewerProps {
  content: string;
  title?: string;
  className?: string;
  readOnly?: boolean;
  onSecurityEvent?: (event: CanvasSecurityAuditEvent) => void;
}
