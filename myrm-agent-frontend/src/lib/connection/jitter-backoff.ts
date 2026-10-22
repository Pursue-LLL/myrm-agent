/**
 * 带抖动的指数退避调度器 (Jittered Exponential Backoff Scheduler)。
 *
 * 汲取 DeepSeek Harness 2026-08-28 `web-connection-recovery-control` 核心生产实践：
 * 1. 在线状态下的传输失败进入带抖动的指数退避：上限从 500ms 开始，依次翻倍为 1s、2s、4s、8s，最终封顶 10s；
 * 2. 实际延迟取上限的 50%–100% 随机抖动，杜绝多端惊群冲击；
 * 3. 达到 10s 档重试失败后停止盲目重试，等待用户主动介入。
 */

export interface BackoffOptions {
  baseDelayMs?: number;
  maxDelayMs?: number;
  jitterMinRatio?: number;
  jitterMaxRatio?: number;
}

export class JitteredBackoffScheduler {
  // 严格的 6 档退避阶梯（毫秒）：500ms -> 1s -> 2s -> 4s -> 8s -> 10s
  public static readonly SCHEDULE_TIERS: readonly number[] = [
    500, 1000, 2000, 4000, 8000, 10000,
  ];

  private readonly jitterMinRatio: number;
  private readonly jitterMaxRatio: number;
  private currentAttempt: number = 0;
  private exhausted: boolean = false;

  constructor(options?: BackoffOptions) {
    this.jitterMinRatio = options?.jitterMinRatio ?? 0.5;
    this.jitterMaxRatio = options?.jitterMaxRatio ?? 1.0;
  }

  public get attempt(): number {
    return this.currentAttempt;
  }

  public isExhausted(): boolean {
    return this.exhausted;
  }

  public reset(): void {
    this.currentAttempt = 0;
    this.exhausted = false;
  }

  /**
   * 计算下一轮重试的带抖动延迟时长（毫秒）。
   * @param randomSeed 可选的确定性随机种子（取值 [0.0, 1.0]），供单测精准断言。
   */
  public nextDelayMs(randomSeed?: number): number {
    if (this.exhausted) {
      return 0;
    }

    const tiers = JitteredBackoffScheduler.SCHEDULE_TIERS;
    const tierIndex = Math.min(this.currentAttempt, tiers.length - 1);
    const tierCap = tiers[tierIndex];

    // 如果尝试次数已经达到阶梯数量之后，判定为耗尽并优雅停止
    if (this.currentAttempt >= tiers.length) {
      this.exhausted = true;
      return 0;
    }

    const seed = randomSeed ?? Math.random();
    const ratio = this.jitterMinRatio + seed * (this.jitterMaxRatio - this.jitterMinRatio);
    const clampedRatio = Math.max(this.jitterMinRatio, Math.min(this.jitterMaxRatio, ratio));

    const delay = Math.round(tierCap * clampedRatio);
    this.currentAttempt += 1;
    return delay;
  }
}
