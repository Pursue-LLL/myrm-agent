/**
 * [INPUT]
 * - CanvasViewer.tsx
 * - CanvasSecurityBridge.ts
 * - useCanvasGatingStore.ts
 * - canvasSecurityTypes.ts
 *
 * [OUTPUT]
 * - Facade exports for Canvas safe sandboxing and interactive script gating (Item 44 P0)
 *
 * [POS]
 * Public API of Canvas security gating feature.
 * Strictly under 40 lines. Zero `any`.
 */

export { CanvasViewer } from './CanvasViewer';
export {
  STRICT_SANDBOX_POLICY,
  STRICT_CSP_META,
  compileSandboxedHtml,
  validateInboundCanvasMessage,
} from './CanvasSecurityBridge';
export { useCanvasGatingStore } from './useCanvasGatingStore';
export type {
  CanvasSandboxPolicy,
  CanvasPermissionStatus,
  CanvasEgressRequest,
  CanvasAuditEventType,
  CanvasSecurityAuditEvent,
  CanvasViewerProps,
} from './canvasSecurityTypes';
