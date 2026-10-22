/**
 * upgrade-cockpit - 一键无感升级控制台门面导出
 *
 * [INPUT]
 * - upgradeCockpitTypes: 数据契约
 * - useUpgradePreFlightDiagnostics: 核心调度 Hook
 * - UpgradePreFlightProbeCard: 前置网络体检大盘
 * - ActiveTaskDrainSafetyBanner: 长任务防误杀横幅
 * - DualInstanceHandoffPipelineModal: 双实例流水线模态框
 *
 * [OUTPUT]
 * - 导出全部核心契约与 UI 组件
 *
 * [POS]
 * 系统一键无感升级控制台公共门面。
 */

export * from './upgradeCockpitTypes';
export * from './useUpgradePreFlightDiagnostics';
export * from './UpgradePreFlightProbeCard';
export * from './ActiveTaskDrainSafetyBanner';
export * from './DualInstanceHandoffPipelineModal';
