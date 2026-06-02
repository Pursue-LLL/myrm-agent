/**
 * [INPUT]
 * (none — standalone utility)
 *
 * [OUTPUT]
 * selectFrames: Selects key frames from a buffer using uniform sampling + first/last preservation + minGap deduplication
 * VisualFrame / FrameSelectionOptions / FrameSelectionResult types
 *
 * [POS]
 * Intelligent frame selector. Reduces visual frames sent to LLM while preserving temporal coverage.
 */

export interface VisualFrame {
  id: string;
  base64: string;
  width: number;
  height: number;
  timestamp: number;
}

export interface FrameSelectionOptions {
  maxFrames: number;
  minGapMs: number;
  preserveFirstLast: boolean;
}

export interface FrameSelectionResult {
  frames: VisualFrame[];
  reason: 'full' | 'sampled';
}

const DEFAULT_OPTIONS: FrameSelectionOptions = {
  maxFrames: 7,
  minGapMs: 120,
  preserveFirstLast: true,
};

function dedupeById(frames: VisualFrame[]): VisualFrame[] {
  const seen = new Set<string>();
  return frames.filter((f) => {
    if (seen.has(f.id)) return false;
    seen.add(f.id);
    return true;
  });
}

function applyMinGap(frames: VisualFrame[], minGapMs: number): VisualFrame[] {
  const sorted = [...frames].sort((a, b) => a.timestamp - b.timestamp);
  const result: VisualFrame[] = [];
  for (const frame of sorted) {
    const last = result.at(-1);
    if (!last || frame.timestamp - last.timestamp >= minGapMs) {
      result.push(frame);
    }
  }
  return result;
}

export function selectFrames(
  candidates: VisualFrame[],
  options: Partial<FrameSelectionOptions> = {},
): FrameSelectionResult {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  if (candidates.length === 0) {
    return { frames: [], reason: 'full' };
  }

  if (candidates.length <= opts.maxFrames) {
    return {
      frames: applyMinGap(candidates, opts.minGapMs),
      reason: 'full',
    };
  }

  const sampled: VisualFrame[] = [];
  const reservedSlots = opts.preserveFirstLast ? 2 : 0;
  const middleSlots = Math.max(opts.maxFrames - reservedSlots, 0);

  if (opts.preserveFirstLast) {
    sampled.push(candidates[0]);
  }

  if (middleSlots > 0) {
    const middle = candidates.slice(1, -1);
    for (let i = 0; i < middleSlots; i++) {
      const pos = Math.floor(((i + 1) * middle.length) / (middleSlots + 1));
      const frame = middle[Math.min(pos, Math.max(middle.length - 1, 0))];
      if (frame) sampled.push(frame);
    }
  }

  if (opts.preserveFirstLast && candidates.length > 1) {
    sampled.push(candidates[candidates.length - 1]);
  }

  return {
    frames: applyMinGap(dedupeById(sampled), opts.minGapMs).slice(0, opts.maxFrames),
    reason: 'sampled',
  };
}
