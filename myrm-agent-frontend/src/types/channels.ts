/**
 * Channel authentication types
 *
 * Matches backend AsyncLoginProtocol types from myrm-agent-harness
 */

export enum LoginMethod {
  QR_CODE = 'qr_code',
  OAUTH2 = 'oauth2',
}

export enum LoginStatus {
  IDLE = 'idle',
  GENERATING = 'generating',
  WAITING_USER_ACTION = 'waiting_user_action',
  VALIDATING = 'validating',
  SUCCESS = 'success',
  FAILED = 'failed',
  TIMEOUT = 'timeout',
  CANCELLED = 'cancelled',
}

export interface LoginState {
  status: LoginStatus;
  method: LoginMethod;
  qr_code_base64?: string;
  qr_expires_at?: string;
  oauth_authorization_url?: string;
  oauth_state_token?: string;
  error_message?: string;
  progress_percent?: number;
}

export interface LoginEvent {
  timestamp: string;
  state: LoginState;
  channel_name: string;
  credentials?: Record<string, unknown>;
}

export interface ChannelInfo {
  channel_id: string;
  channel_name: string;
  supported_methods: LoginMethod[];
  description?: string;
}

export interface StartLoginRequest {
  method: LoginMethod;
}

export interface StartLoginResponse {
  session_id: string;
  channel_id: string;
  method: string;
  stream_url: string;
}
