/**
 * PetStateMachine — maps agent SSE events to Codex/Hermes-aligned pet animation states.
 *
 * [INPUT]
 * - None (standalone state machine, receives events via ingest() calls)
 *
 * [OUTPUT]
 * - PetStateMachine: Event-driven state machine with transient/sticky/release modes
 * - PetState: Seven-state enum aligned with Petdex/Hermes (idle/run/review/jump/wave/failed/waiting)
 * - stepKeyToPetEvent: SSE step_key → PetEvent mapping function
 *
 * [POS]
 * State machine that translates agent SSE status events into pet animation states.
 * Uses transient/sticky/release event modes with heartbeat timeout for idle fallback.
 * Blocked-on-user (approval/clarify) is driven via setBlockedOnUser() from store SSOT in PetOverlay.
 */

/** Codex/Hermes-aligned animation states (not raw spritesheet row indices). */
export enum PetState {
  IDLE = 0,
  RUNNING = 1,
  REVIEWING = 2,
  JUMP = 3,
  WAVE = 4,
  FAILED = 5,
  WAITING = 6,
}

export type EventMode = 'transient' | 'sticky' | 'release';

export interface PetEvent {
  state: PetState;
  mode: EventMode;
  ttlMs?: number;
}

export interface PetStateMachineOptions {
  onChange: (state: PetState) => void;
  heartbeatTimeoutMs?: number;
  tickIntervalMs?: number;
}

const DEFAULT_HEARTBEAT_TIMEOUT_MS = 15_000;
const DEFAULT_TICK_INTERVAL_MS = 250;

const TRANSIENT_DEFAULT_TTL: Record<PetState, number> = {
  [PetState.IDLE]: 0,
  [PetState.RUNNING]: 2000,
  [PetState.REVIEWING]: 2500,
  [PetState.JUMP]: 2000,
  [PetState.WAVE]: 1500,
  [PetState.FAILED]: 2500,
  [PetState.WAITING]: 0,
};

/**
 * Maps SSE step_key values to PetEvent configs.
 * Approval/clarify waiting is NOT mapped here — use setBlockedOnUser() instead.
 */
export function stepKeyToPetEvent(stepKey: string): PetEvent | null {
  switch (stepKey) {
    case 'workflow_init':
    case 'workflow_planning':
    case 'consensus_active':
    case 'moa_overlay_active':
      return { state: PetState.REVIEWING, mode: 'sticky' };

    case 'workflow_execution':
    case 'workflow_stage':
      return { state: PetState.RUNNING, mode: 'sticky' };

    case 'context_compaction':
    case 'context_truncation':
    case 'context_pruned':
    case 'memory_archived':
    case 'correction_learned':
      return { state: PetState.REVIEWING, mode: 'transient', ttlMs: 2000 };

    case 'model_failover':
    case 'model_failover_unconfigured':
    case 'safety_fallback_unconfigured':
    case 'safety_fallback_active':
    case 'transient_retry':
      return { state: PetState.FAILED, mode: 'transient', ttlMs: 2500 };

    case 'thinking_budget_exhausted':
    case 'text_continuation_exhausted':
      return { state: PetState.FAILED, mode: 'transient', ttlMs: 2000 };

    case 'analyzing_image':
    case 'analyzing_video':
      return { state: PetState.REVIEWING, mode: 'sticky' };

    case 'consensus_reference_done':
    case 'moa_ref_done':
      return { state: PetState.JUMP, mode: 'transient', ttlMs: 1500 };

    case 'loop_guard_warn':
      return { state: PetState.REVIEWING, mode: 'transient', ttlMs: 2000 };

    case 'loop_guard_break':
      return { state: PetState.FAILED, mode: 'transient', ttlMs: 3000 };

    default:
      return null;
  }
}

export class PetStateMachine {
  private onChange: (state: PetState) => void;
  private heartbeatTimeoutMs: number;

  private currentState: PetState = PetState.IDLE;
  private stickyState: PetState | null = null;
  private transientUntil: number | null = null;
  private blockedOnUser = false;
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
    if (this.destroyed) {return;}

    switch (event.mode) {
      case 'transient': {
        const ttl = event.ttlMs ?? TRANSIENT_DEFAULT_TTL[event.state] ?? 2000;
        this.transientUntil = Date.now() + ttl;
        this.setState(event.state);
        break;
      }
      case 'sticky':
        this.stickyState = event.state;
        this.transientUntil = null;
        this.setState(event.state);
        break;
      case 'release':
        this.stickyState = null;
        break;
    }
  }

  /**
   * User-blocked signal (approval/clarify/desktop/browser).
   * Sourced from existing frontend stores — not SSE step_key dispatches.
   */
  setBlockedOnUser(blocked: boolean) {
    if (this.blockedOnUser === blocked) {return;}
    this.blockedOnUser = blocked;
    this.tick();
  }

  /** Send a heartbeat to prevent idle timeout. */
  heartbeat() {
    this.lastHeartbeat = Date.now();
  }

  /** Signal that the agent is loading (streaming in progress). */
  setLoading(loading: boolean) {
    if (loading) {
      this.ingest({ state: PetState.REVIEWING, mode: 'sticky' });
      this.heartbeat();
      return;
    }

    if (!this.blockedOnUser) {
      this.ingest({ state: PetState.WAVE, mode: 'transient', ttlMs: 1500 });
      this.stickyState = null;
    }
  }

  /** Force transition to idle. */
  reset() {
    this.stickyState = null;
    this.transientUntil = null;
    this.blockedOnUser = false;
    this.setState(PetState.IDLE);
  }

  getCurrentState(): PetState {
    return this.currentState;
  }

  destroy() {
    this.destroyed = true;
    if (this.tickTimer !== null) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
  }

  private tick() {
    if (this.destroyed) {return;}

    if (this.blockedOnUser) {
      this.setState(PetState.WAITING);
      return;
    }

    if (this.transientUntil !== null) {
      if (Date.now() < this.transientUntil) {return;}
      this.transientUntil = null;
    }

    if (Date.now() - this.lastHeartbeat > this.heartbeatTimeoutMs) {
      this.stickyState = null;
      this.setState(PetState.IDLE);
      return;
    }

    this.setState(this.stickyState ?? PetState.IDLE);
  }

  private setState(state: PetState) {
    if (state === this.currentState) {return;}
    this.currentState = state;
    this.onChange(state);
  }
}
