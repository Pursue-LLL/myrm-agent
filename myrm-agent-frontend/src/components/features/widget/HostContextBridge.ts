/**
 * [INPUT]
 * - widgetTypes: HostBridgeMessage, HostContextSnapshot, HostBridgeAction
 * - useWidgetBridgeStore: Zustand store instance
 *
 * [OUTPUT]
 * - HostContextBridge: Bi-directional secure cross-origin postMessage IPC bridge
 *
 * [POS]
 * Cross-origin IPC bridge layer for Embeddable Agent Widget (Item 41 P1).
 * Strictly under 160 lines. Zero `any`.
 */

import type { HostBridgeMessage, HostContextSnapshot } from "./widgetTypes";
import { useWidgetBridgeStore } from "./useWidgetBridgeStore";

export class HostContextBridge {
  private static listenerAttached = false;
  private static messageHandler: ((event: MessageEvent<unknown>) => void) | null = null;

  public static isOriginAllowed(origin: string, allowedOrigins: string[]): boolean {
    if (!origin) {
      return false;
    }
    if (allowedOrigins.includes("*")) {
      return true;
    }

    const normalizedOrigin = origin.trim().replace(/\/$/, "").toLowerCase();
    for (const allowed of allowedOrigins) {
      const cleaned = allowed.trim().replace(/\/$/, "").toLowerCase();
      if (cleaned === normalizedOrigin) {
        return true;
      }
      if (cleaned.startsWith("*.")) {
        const domainPart = cleaned.slice(2);
        try {
          const url = new URL(normalizedOrigin);
          if (url.hostname === domainPart || url.hostname.endsWith("." + domainPart)) {
            return true;
          }
        } catch {
          // Ignore invalid URL
        }
      }
    }
    return false;
  }

  public static initialize(chatId: string, onPromptTriggered?: (prompt: string) => void): () => void {
    if (typeof window === "undefined") {
      return () => {};
    }

    if (this.listenerAttached && this.messageHandler) {
      window.removeEventListener("message", this.messageHandler);
    }

    this.messageHandler = (event: MessageEvent<unknown>) => {
      const store = useWidgetBridgeStore.getState();
      const origin = event.origin;

      if (!this.isOriginAllowed(origin, store.allowedOrigins)) {
        return;
      }

      const data = event.data;
      if (typeof data !== "object" || data === null) {
        return;
      }

      const rawMsg = data as Record<string, unknown>;
      if (typeof rawMsg.action !== "string") {
        return;
      }

      const message: HostBridgeMessage = {
        action: rawMsg.action as HostBridgeMessage["action"],
        payload: (typeof rawMsg.payload === "object" && rawMsg.payload !== null
          ? (rawMsg.payload as Record<string, string>)
          : {}) as Record<string, string>,
        timestampMs: typeof rawMsg.timestampMs === "number" ? rawMsg.timestampMs : Date.now(),
        origin,
      };

      store.appendMessage(message);

      switch (message.action) {
        case "sync_context": {
          if (message.payload && message.payload.currentUrl) {
            const snapshot: HostContextSnapshot = {
              origin,
              currentUrl: message.payload.currentUrl,
              pageTitle: message.payload.pageTitle,
              selectedText: message.payload.selectedText,
              formFields: message.payload.formFields
                ? (JSON.parse(message.payload.formFields) as Record<string, string>)
                : {},
              userMetadata: message.payload.userMetadata
                ? (JSON.parse(message.payload.userMetadata) as Record<string, string>)
                : {},
              capturedAtMs: Date.now(),
            };
            void store.injectHostContext(chatId, snapshot);
          }
          break;
        }

        case "trigger_prompt": {
          const prompt = message.payload?.prompt;
          if (prompt && onPromptTriggered) {
            onPromptTriggered(prompt);
          }
          break;
        }

        case "toggle_widget": {
          store.setWidgetOpen(!store.isWidgetOpen);
          break;
        }

        case "close_widget": {
          store.setWidgetOpen(false);
          break;
        }

        case "ping": {
          this.postToHost({
            action: "pong",
            payload: { status: "ready", chatId },
            origin,
          });
          break;
        }

        default:
          break;
      }
    };

    window.addEventListener("message", this.messageHandler);
    this.listenerAttached = true;

    // Send initial handshake to parent if embedded in iframe
    this.postToHost({
      action: "ping",
      payload: { client: "myrm-agent-widget", chatId },
    });

    return () => {
      if (this.messageHandler) {
        window.removeEventListener("message", this.messageHandler);
        this.messageHandler = null;
        this.listenerAttached = false;
      }
    };
  }

  public static postToHost(message: HostBridgeMessage): void {
    if (typeof window === "undefined" || window.parent === window) {
      return;
    }
    const targetOrigin = message.origin && message.origin !== "*" ? message.origin : "*";
    window.parent.postMessage(message, targetOrigin);
  }

  public static notifyResize(width: number, height: number): void {
    this.postToHost({
      action: "resize_viewport",
      payload: { width: String(width), height: String(height) },
    });
  }
}
