/**
 * [INPUT]
 * (none — standalone type)
 *
 * [OUTPUT]
 * VisualFrame: One screenshot attached to a voice message
 *
 * [POS]
 * Shape of the frames a voice session hands to the chat when a message carries a push-to-talk screenshot.
 */

export interface VisualFrame {
  id: string;
  base64: string;
  width: number;
  height: number;
  timestamp: number;
}
