export type StreamConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'streaming'
  | 'paused'
  | 'error';

export type ControlMode = 'observer' | 'human-takeover';

export interface StreamQualityMetrics {
  fps: number;
  latencyMs: number;
  bitrateKbps: number;
  resolution: string;
}

export type ActionTelemetryType =
  | 'click'
  | 'type'
  | 'scroll'
  | 'navigate'
  | 'captcha-detected';

export interface DesktopActionTelemetry {
  id: string;
  actionType: ActionTelemetryType;
  description: string;
  coordinates?: { x: number; y: number };
  timestamp: number;
}

export interface EphemeralShareTicket {
  ticketId: string;
  sandboxId: string;
  expiresAt: number;
  signature: string;
  url: string;
  allowTakeover: boolean;
  oneTimeOnly: boolean;
}

export interface ShareOptions {
  ttlSeconds: number; // e.g. 3600, 7200, 86400
  allowTakeover: boolean;
  oneTimeOnly: boolean;
}
