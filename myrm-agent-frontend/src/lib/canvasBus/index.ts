/**
 * [INPUT]
 * ./multiWindowCanvasStateBus::MultiWindowCanvasStateBus
 * ./streamBackpressureController::StreamBackpressureController
 *
 * [OUTPUT]
 * Re-exports of cross-window canvas bus and stream backpressure controller
 *
 * [POS]
 * myrm-agent-frontend/src/lib/canvasBus/index.ts
 */

export {
  MultiWindowCanvasStateBus,
  type CanvasBusEvent,
  type CanvasBusEventHandler,
  type CanvasBusEventType,
  type SessionFocusEvent,
  type CanvasStateUpdateEvent,
  type ToolExecutionSyncEvent,
  type ConfigSyncEvent,
} from './multiWindowCanvasStateBus';

export {
  StreamBackpressureController,
  type BackpressureConfig,
  type BackpressureMetrics,
  type StreamRenderCallback,
} from './streamBackpressureController';
