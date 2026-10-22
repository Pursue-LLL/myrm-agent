import { ArtifactPlayItem } from './skeuomorphicTypes';

/**
 * 计算鼠标/触摸点相对于转盘中心的平面角度 (0 ~ 360 度)
 */
export function calculateWheelAngle(
  clientX: number,
  clientY: number,
  centerX: number,
  centerY: number
): number {
  const dx = clientX - centerX;
  const dy = clientY - centerY;
  const rad = Math.atan2(dy, dx);
  let deg = (rad * 180) / Math.PI + 90;
  if (deg < 0) {
    deg += 360;
  }
  return deg;
}

/**
 * 根据角位移计算转盘棘轮步进跳变值（防止跨越 0°/360° 突变）
 */
export function calculateAngularStepDelta(
  currentAngle: number,
  previousAngle: number,
  stepDegreeThreshold = 20
): { stepDelta: number; remainingAngle: number } {
  let delta = currentAngle - previousAngle;
  if (delta > 180) {
    delta -= 360;
  } else if (delta < -180) {
    delta += 360;
  }

  if (Math.abs(delta) >= stepDegreeThreshold) {
    const steps = Math.trunc(delta / stepDegreeThreshold);
    const remainder = delta % stepDegreeThreshold;
    return {
      stepDelta: steps,
      remainingAngle: remainder,
    };
  }

  return {
    stepDelta: 0,
    remainingAngle: delta,
  };
}

/**
 * 环状回绕索引计算
 */
export function wrapArtifactIndex(index: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return ((index % total) + total) % total;
}

/**
 * 格式化任务耗时 (ms -> 分秒)
 */
export function formatTaskDuration(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  const seconds = Math.floor(durationMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const mins = Math.floor(seconds / 60);
  const remSec = seconds % 60;
  return `${mins}m ${remSec}s`;
}

/**
 * 格式化 Token 计数 (如 1.2k tokens)
 */
export function formatTokenUsage(tokens: number): string {
  if (tokens < 1000) {
    return `${tokens} T`;
  }
  return `${(tokens / 1000).toFixed(1)}k T`;
}

/**
 * 预设高保真拟物化任务工件示例数据集
 */
export function getDefaultMockArtifacts(): ArtifactPlayItem[] {
  return [
    {
      id: 'art-001',
      taskTitle: '重构前端会话上下文数据获取模型',
      stageName: 'Stage 3: 架构收敛',
      createdAt: '2026-09-08 14:32',
      status: 'completed',
      summary: '聚合 GraphQL 启动包，请求数由 140 骤降至 45，首屏冷启时间降至 575ms。',
      artifactType: 'code',
      tokensUsed: 4230,
      durationMs: 8400,
      authorAgent: 'Arch-Master-4o',
      codeSnippet: 'export const sessionDataBootstrap = async (sessionId: string) => { ... }',
    },
    {
      id: 'art-002',
      taskTitle: '设计拟物化复古 iPod 风格任务旋转播放器',
      stageName: 'Stage 4: 拟物化视效交付',
      createdAt: '2026-09-08 15:10',
      status: 'completed',
      summary: '高仿经典 Click Wheel 机械旋钮、单色点阵液晶面板与物理棘轮音效。',
      artifactType: 'design',
      tokensUsed: 3120,
      durationMs: 5200,
      authorAgent: 'UX-Aesthetics-Bot',
    },
    {
      id: 'art-003',
      taskTitle: '执行沙箱硬件遥测与内存泄漏排查',
      stageName: 'Stage 2: 运行时压力测试',
      createdAt: '2026-09-08 15:45',
      status: 'completed',
      summary: '采集 cgroups v2 内存水位与 CPU 节流时延，生成健康自检报告与火焰图。',
      artifactType: 'preview',
      tokensUsed: 6890,
      durationMs: 14500,
      authorAgent: 'Diagnostics-Reaper',
    },
    {
      id: 'art-004',
      taskTitle: '拍立得照片墙即时冲印与版本工件交付',
      stageName: 'Stage 5: 多媒体工件归档',
      createdAt: '2026-09-08 16:02',
      status: 'completed',
      summary: '模拟经典拍立得白边相纸冲印动效，支持手写签名备注与多媒体留影。',
      artifactType: 'media',
      tokensUsed: 2750,
      durationMs: 4100,
      authorAgent: 'Polaroid-Curator',
    },
  ];
}
