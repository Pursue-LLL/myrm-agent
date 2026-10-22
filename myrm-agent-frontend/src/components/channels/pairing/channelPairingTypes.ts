/**
 * Channel Pairing & Handshake Protocol Frontend Types.
 *
 * Strict zero-any TypeScript interfaces.
 */

export type ChannelPlatform =
  | 'wechat'
  | 'wecom'
  | 'feishu'
  | 'dingtalk'
  | 'slack'
  | 'telegram';

export type PairingSessionStatus =
  | 'pending'
  | 'scanned'
  | 'authenticated'
  | 'failed'
  | 'expired';

export type PairingWizardStep =
  | 'select_platform'
  | 'scan_handshake'
  | 'confirm_binding'
  | 'health_check';

export interface PairingQRCode {
  pairing_url: string;
  qr_matrix_base64: string;
  expires_in_seconds: number;
}

export interface PairingSessionResponse {
  session_id: string;
  platform: ChannelPlatform;
  status: PairingSessionStatus;
  qr_code: PairingQRCode | null;
  bound_token_masked: string | null;
  user_identity: string | null;
  created_at_epoch_ms: number;
  error_message: string | null;
}

export interface PairingSessionCreatePayload {
  platform: ChannelPlatform;
  channel_instance_id?: string;
  custom_label?: string;
}

export interface PairingConfirmPayload {
  auth_token: string;
  user_identity?: string;
}

export interface PairingConfirmResponse {
  session_id: string;
  platform: ChannelPlatform;
  status: PairingSessionStatus;
  persisted: boolean;
  message: string;
}

export interface ChannelPingPayload {
  platform: ChannelPlatform;
  target_recipient?: string;
  test_message?: string;
}

export interface ChannelPingResponse {
  platform: ChannelPlatform;
  success: boolean;
  latency_ms: number;
  receipt_id: string;
  dispatched_at_epoch_ms: number;
  error_detail: string | null;
}

export interface PlatformMetadata {
  id: ChannelPlatform;
  nameKey: string;
  descKey: string;
  brandColor: string;
  guideKey: string;
}
