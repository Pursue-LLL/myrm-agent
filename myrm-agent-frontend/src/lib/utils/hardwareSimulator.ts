/**
 * Hardware Reference Ladder & 64k Context KV Cache memory estimation utilities.
 */

export interface HardwareRungInfo {
  rung: number;
  name: string;
  minVramGb: number;
  recommendedModels: string;
  description: string;
}

export const HARDWARE_RUNGS: HardwareRungInfo[] = [
  {
    rung: 1,
    name: 'Entry (< 10GB)',
    minVramGb: 4,
    recommendedModels: '0.5B ~ 3B',
    description: '适合轻量级任务，内存较小，建议使用超轻量模型',
  },
  {
    rung: 2,
    name: 'Mainstream (10 - 20GB)',
    minVramGb: 10,
    recommendedModels: '8B (Q4_K_M)',
    description: '主流配置（如 16GB Mac/PC），可平稳运行 8B 模型的 64k 任务',
  },
  {
    rung: 3,
    name: 'High-end (20 - 40GB)',
    minVramGb: 20,
    recommendedModels: '14B (Q4) / 8B (FP16)',
    description: '高配工作站（如 32GB Mac/RTX 4090 24G），高智能且长上下文充裕',
  },
  {
    rung: 4,
    name: 'Workstation (40 - 80GB)',
    minVramGb: 40,
    recommendedModels: '32B (MoE/Dense)',
    description: '专业工作站（如 64GB Mac/A6000），可胜任复杂长任务深度推理',
  },
  {
    rung: 5,
    name: 'Flagship (80GB+)',
    minVramGb: 80,
    recommendedModels: '70B+ 旗舰',
    description: '顶级算力（如 128GB+ Mac Studio/多卡集群），运行全尺寸旗舰模型',
  },
];

export function calculateKvCacheVramGb(
  numLayers: number,
  kvHeads: number,
  headDim: number,
  contextLength = 65536,
  bytesPerElem = 2.0,
): number {
  if (numLayers <= 0 || kvHeads <= 0 || headDim <= 0 || contextLength <= 0) {
    return 0;
  }
  const rawBytes = 2 * numLayers * kvHeads * headDim * contextLength * bytesPerElem;
  return Math.round((rawBytes / Math.pow(1024, 3)) * 100) / 100;
}

export function getRungByVram(vramGb: number): HardwareRungInfo {
  if (vramGb < 10) return HARDWARE_RUNGS[0];
  if (vramGb < 20) return HARDWARE_RUNGS[1];
  if (vramGb < 40) return HARDWARE_RUNGS[2];
  if (vramGb < 80) return HARDWARE_RUNGS[3];
  return HARDWARE_RUNGS[4];
}
