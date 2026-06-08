/**
 * PetStateMachine — maps agent SSE events to spritesheet animation rows.
 *
 * Inspired by clawdex StateMachine.swift's transient/sticky/release model:
 *  - transient: play a row for one cycle duration, then return to base.
 *  - sticky: hold a row until another event or release arrives.
 *  - heartbeat: keep-alive; absence (>15s) falls back to idle.
 *
 * Row mapping follows the Codex standard 8×9 atlas:
 *  0=idle, 1=running, 2=sleeping, 3=coding, 4=thinking,
 *  5=celebrating, 6=failed, 7=reviewing, 8=waving
 */

export enum AnimRow {
  IDLE = 0,
  RUNNING = 1,
  SLEEPING = 2,
  CODING = 3,
  THINKING = 4,
  CELEBRATING = 5,
  FAILED = 6,
  REVIEWING = 7,
  WAVING = 8,
}

export type EventMode = 'transient' | 'sticky' | 'release';

export interface PetEvent {
  row: AnimRow;
  mode: EventMode;
  ttlMs?: number;
}

export interface PetStateMachineOptions {
  onChange: (row: AnimRow) => void;
  heartbeatTimeoutMs?: number;
  tickIntervalMs?: number;
}

const DEFAULT_HEARTBEAT_TIMEOUT_MS = 15_000;
const DEFAULT_TICK_INTERVAL_MS = 250;

const TRANSIENT_DEFAULT_TTL: Record<AnimRow, number> = {
  [AnimRow.IDLE]: 0,
  [AnimRow.RUNNING]: 2000,
  [AnimRow.SLEEPING]: 0,
  [AnimRow.CODING]: 3000,
  [AnimRow.THINKING]: 2500,
  [AnimRow.CELEBRATING]: 2000,
  [AnimRow.FAILED]: 2500,
  [AnimRow.REVIEWING]: 2000,
  [AnimRow.WAVING]: 1500,
};

/**
 * Maps SSE step_key values to PetEvent configs.
 * This is the authoritative mapping between agent status events and pet animations.
 */
export function stepKeyToPetEvent(stepKey: string): PetEvent | null {
  switch (stepKey) {
    case 'workflow_init':
    case 'workflow_planning':
      return { row: AnimRow.THINKING, mode: 'sticky' };

    case 'workflow_execution':
    case 'workflow_stage':
      return { row: AnimRow.RUNNING, mode: 'sticky' };

    case 'context_compaction':
    case 'context_truncation':
    case 'context_pruned':
    case 'memory_archived':
      return { row: AnimRow.REVIEWING, mode: 'transient', ttlMs: 2000 };

    case 'model_failover':
    case 'safety_fallback_active':
    case 'transient_retry':
      return { row: AnimRow.FAILED, mode: 'transient', ttlMs: 2500 };

    case 'thinking_budget_exhausted':
    case 'text_continuation_exhausted':
      return { row: AnimRow.FAILED, mode: 'transient', ttlMs: 2000 };

    case 'analyzing_image':
    case 'analyzing_video':
      return { row: AnimRow.REVIEWING, mode: 'sticky' };

    case 'consensus_active':
      return { row: AnimRow.THINKING, mode: 'sticky' };

    case 'consensus_reference_done':
      return { row: AnimRow.CELEBRATING, mode: 'transient', ttlMs: 1500 };

    case 'loop_guard_warn':
      return { row: AnimRow.REVIEWING, mode: 'transient', ttlMs: 2000 };

    case 'loop_guard_break':
      return { row: AnimRow.FAILED, mode: 'transient', ttlMs: 3000 };

    default:
      return null;
  }
}

export class PetStateMachine {
  private onChange: (row: AnimRow) => void;
  private heartbeatTimeoutMs: number;

  private currentRow: AnimRow = AnimRow.IDLE;
  private stickyRow: AnimRow | null = null;
  private transientUntil: number | null = null;
  private lastHeartbeat: number = Date.now();
  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private destroyed = false;

  constructor(options: PetStateMachineOptions) {
    this.onChange = options.onChange;
    this.heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? DEFAULT_HEARTBEAT_TIMEOUT_MS;

    this.tickTimer = setInterval(
      () => this.tick(),
      options.tickIntervalMs ?? DEFAULT_TICK_INTERVAL_MS,
    );
  }

  /** Process an incoming event. */
  ingest(event: PetEvent) {
    if (this.destroyed) return;

    switch (event.mode) {
      case 'transient': {
        const ttl = event.ttlMs ?? TRANSIENT_DEFAULT_TTL[event.row] ?? 2000;
        this.transientUntil = Date.now() + ttl;
        this.setRow(event.row);
        break;
      }
      case 'sticky':
        this.stickyRow = event.row;
        this.transientUntil = null;
        this.setRow(event.row);
        break;
      case 'release':
        this.stickyRow = null;
        break;
    }
  }

  /** Send a heartbeat to prevent idle timeout. */
  heartbeat() {
    this.lastHeartbeat = Date.now();
  }

  /** Signal that the agent is loading (streaming in progress). */
  setLoading(loading: boolean) {
    if (loading) {
      this.ingest({ row: AnimRow.THINKING, mode: 'sticky' });
      this.heartbeat();
    } else {
      this.ingest({ row: AnimRow.CELEBRATING, mode: 'transient', ttlMs: 1500 });
      this.stickyRow = null;
    }
  }

  /** Force transition to idle. */
  reset() {
    this.stickyRow = null;
    this.transientUntil = null;
    this.setRow(AnimRow.IDLE);
  }

  getCurrentRow(): AnimRow {
    return this.currentRow;
  }

  destroy() {
    this.destroyed = true;
    if (this.tickTimer !== null) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
  }

  private tick() {
    if (this.destroyed) return;

    // Transient still playing? Hold.
    if (this.transientUntil !== null) {
      if (Date.now() < this.transientUntil) return;
      this.transientUntil = null;
    }

    // Heartbeat timeout → force idle
    if (Date.now() - this.lastHeartbeat > this.heartbeatTimeoutMs) {
      this.stickyRow = null;
      this.setRow(AnimRow.IDLE);
      return;
    }

    // Default: sticky if set, else idle
    this.setRow(this.stickyRow ?? AnimRow.IDLE);
  }

  private setRow(row: AnimRow) {
    if (row === this.currentRow) return;
    this.currentRow = row;
    this.onChange(row);
  }
}
