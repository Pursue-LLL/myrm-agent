/**
 * upgradeCockpitTypes - 一键无感升级控制台与长任务热重载数据契约
 *
 * [INPUT]
 * - 无外部运行时依赖
 *
 * [OUTPUT]
 * - NetworkMirrorProbeResult: 多源网络探针体检结果
 * - ActiveTaskDrainSafetyCheck: 活动长任务安全排空核验
 * - UpgradeStage: 升级流水线五阶段枚举
 * - UpgradeStageStep: 阶段步进进度定义
 * - RollbackSnapshotMetadata: 一键无损回滚快照元数据
 *
 * [POS]
 * 系统一键无感升级控制台的数据类型事实源。
 */

/**
 * 网络镜像健康度状态
 */
export type MirrorHealthStatus = 'optimal' | 'healthy' | 'degraded' | 'blocked';

/**
 * 多源网络镜像体检探针结果
 */
export interface NetworkMirrorProbeResult {
  /** 镜像唯一标识 (如 github, cnb, tsinghua, npm) */
  id: string;
  /** 镜像显示名称 */
  name: string;
  /** 探测端点 URL */
  endpointUrl: string;
  /** 往返网络延迟 (ms) */
  latencyMs: number;
  /** 健康度状态评估 */
  status: MirrorHealthStatus;
  /** 是否由智能算法推荐为当前最优镜像 */
  isRecommended: boolean;
  /** 状态描述提示 */
  statusDescription: string;
}

/**
 * 活动长任务防误杀安全决策建议
 */
export type TaskSafetyRecommendation =
  | 'safe_to_reload'
  | 'drain_first'
  | 'checkpoint_and_upgrade';

/**
 * 正在执行的活动任务摘要
 */
export interface ActiveTaskItemSummary {
  id: string;
  type: 'goal' | 'cron' | 'turn';
  title: string;
  progressPercent: number;
}

/**
 * 活动长任务排空与防误杀核验结果
 */
export interface ActiveTaskDrainSafetyCheck {
  /** 是否存在正在执行中的长程 Goal */
  hasActiveGoal: boolean;
  /** 是否存在正在执行中的 Cron 定时任务 */
  hasActiveCron: boolean;
  /** 活动任务总数 */
  activeTaskCount: number;
  /** 活动任务摘要明细 */
  activeTasks: ActiveTaskItemSummary[];
  /** 系统安全决策推荐 */
  recommendation: TaskSafetyRecommendation;
  /** 决策提示理由 */
  recommendationRationale: string;
}

/**
 * 升级阶段枚举（五阶段原子化双实例流水线）
 */
export type UpgradeStage =
  | 'idle'
  | 'snapshot_diff'
  | 'source_pull'
  | 'dependency_heal'
  | 'blue_green_standby'
  | 'health_self_check'
  | 'complete'
  | 'rolled_back'
  | 'failed';

/**
 * 升级阶段执行步进状态
 */
export interface UpgradeStageStep {
  stage: UpgradeStage;
  title: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progressPercent?: number;
  errorMessage?: string;
}

/**
 * 一键秒级原子回滚快照元信息
 */
export interface RollbackSnapshotMetadata {
  snapshotId: string;
  timestamp: string;
  previousVersion: string;
  targetVersion: string;
  sizeBytes: number;
}
