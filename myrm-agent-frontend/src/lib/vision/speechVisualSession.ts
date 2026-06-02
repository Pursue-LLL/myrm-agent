/**
 * [INPUT]
 * (none — standalone utility)
 *
 * [OUTPUT]
 * SpeechVisualSession: Aligns speech timing with visual frame capture window
 * SpeechVisualWindow type
 *
 * [POS]
 * Speech-visual time synchronizer. Ensures captured frames match the temporal range of user speech.
 */

export interface SpeechVisualWindow {
  speechStartAt: number;
  speechEndAt: number;
  preRollMs: number;
  postRollMs: number;
  frameWindowStartAt: number;
  frameWindowEndAt: number;
}

const DEFAULT_PRE_ROLL_MS = 500;
const DEFAULT_POST_ROLL_MS = 300;

export class SpeechVisualSession {
  private speechStartAt: number | null = null;
  private speechEndAt: number | null = null;

  beginSpeech(timestamp: number = Date.now()): void {
    if (this.speechStartAt === null) {
      this.speechStartAt = timestamp;
    }
    this.speechEndAt = null;
  }

  endSpeech(
    timestamp: number = Date.now(),
    preRollMs: number = DEFAULT_PRE_ROLL_MS,
    postRollMs: number = DEFAULT_POST_ROLL_MS,
  ): SpeechVisualWindow | null {
    if (this.speechStartAt === null) return null;
    this.speechEndAt = timestamp;

    return {
      speechStartAt: this.speechStartAt,
      speechEndAt: this.speechEndAt,
      preRollMs,
      postRollMs,
      frameWindowStartAt: this.speechStartAt - preRollMs,
      frameWindowEndAt: this.speechEndAt + postRollMs,
    };
  }

  reset(): void {
    this.speechStartAt = null;
    this.speechEndAt = null;
  }
}
