/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - WidgetDisplayMode, WidgetTheme, HostContextSnapshot, HostBridgeMessage, EmbedSecurityConfig, WidgetGeneratorOptions
 *
 * [POS]
 * Type definitions for Embeddable Agent Widget & Host Context Bridge (Item 41 P1).
 * Strictly under 120 lines. Zero `any`.
 */

export type WidgetDisplayMode = "floating_bubble" | "slideout_drawer" | "inline_container";

export type WidgetTheme = "light" | "dark" | "auto";

export interface HostContextSnapshot {
  origin: string;
  currentUrl: string;
  pageTitle?: string;
  selectedText?: string;
  formFields?: Record<string, string>;
  userMetadata?: Record<string, string>;
  capturedAtMs?: number;
}

export type HostBridgeAction =
  | "sync_context"
  | "trigger_prompt"
  | "resize_viewport"
  | "toggle_widget"
  | "close_widget"
  | "ping"
  | "pong";

export interface HostBridgeMessage {
  action: HostBridgeAction;
  payload?: Record<string, string>;
  timestampMs?: number;
  origin?: string;
}

export interface EmbedSecurityConfig {
  allowedOrigins: string[];
  allowFormCapture: boolean;
  allowSelectionCapture: boolean;
}

export interface WidgetGeneratorOptions {
  mode: WidgetDisplayMode;
  theme: WidgetTheme;
  allowedOrigin: string;
  baseUrl: string;
}
