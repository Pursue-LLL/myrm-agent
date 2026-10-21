/**
 * Cross-Device Hot-Drop & Wireless Camera Beam Types
 * 跨设备近场零摩擦素材直投与无线外设相机通道类型契约
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 字段完备语义化。
 */

export type BeamConnectionState =
  | 'idle'
  | 'pairing'
  | 'connected'
  | 'beaming'
  | 'completed'
  | 'error';

export type BeamTransportMode = 'webrtc' | 'local_ws' | 'relay_e2ee';

export interface BeamPayload {
  id: string;
  sourceDeviceName: string;
  fileName: string;
  fileSizeBytes: number;
  mimeType: string;
  dataUrl: string;
  capturedTimestamp: number;
  ocrExtractedText?: string;
  suggestedPrompt?: string;
}

export interface BeamSessionDescriptor {
  channelId: string;
  pairCode: string;
  qrPayloadUrl: string;
  transportMode: BeamTransportMode;
  connectedDeviceName: string | null;
  connectionState: BeamConnectionState;
  createdAtTimestamp: number;
  expiresInSeconds: number;
}

export interface HotDropInjectionResult {
  payloadId: string;
  injectedAtTimestamp: number;
  targetInputSelector: string;
  status: 'injected' | 'cancelled';
}
