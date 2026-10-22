import { RadialPosition, StarMapNode, TimeBucket } from './starMapTypes';

export interface RadialLayoutConfig {
  centerX: number;
  centerY: number;
  innerRadius: number;
  outerRadius: number;
}

export const DEFAULT_RADIAL_CONFIG: RadialLayoutConfig = {
  centerX: 300,
  centerY: 300,
  innerRadius: 40,
  outerRadius: 260,
};

export function computeStringHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

export function computeRadialPositions(
  nodes: StarMapNode[],
  config = DEFAULT_RADIAL_CONFIG
): StarMapNode[] {
  if (nodes.length === 0) {
    return [];
  }

  let minTime = nodes[0].createdAt;
  let maxTime = nodes[0].createdAt;

  for (const node of nodes) {
    if (node.createdAt < minTime) {
      minTime = node.createdAt;
    }
    if (node.createdAt > maxTime) {
      maxTime = node.createdAt;
    }
  }

  const timeSpan = maxTime === minTime ? 1 : maxTime - minTime;
  const radiusSpan = config.outerRadius - config.innerRadius;

  return nodes.map((node, index) => {
    // 径向距离映射：最早在中心，最新在外环
    const recencyRatio = (node.createdAt - minTime) / timeSpan;
    const r = config.innerRadius + recencyRatio * radiusSpan;

    // 极角分布：基于实体 ID 哈希与排列序号离散分布，黄金角步进减少重叠
    const hashVal = computeStringHash(node.id);
    const goldenAngle = 2.399963229728653; // 137.5 degrees in radians
    const theta = ((index * goldenAngle + (hashVal % 100) * 0.05) % (2 * Math.PI));

    const x = config.centerX + r * Math.cos(theta);
    const y = config.centerY + r * Math.sin(theta);

    const radialPosition: RadialPosition = {
      r: Math.round(r * 100) / 100,
      theta: Math.round(theta * 1000) / 1000,
      x: Math.round(x * 10) / 10,
      y: Math.round(y * 10) / 10,
    };

    return {
      ...node,
      radialPosition,
    };
  });
}

export function computeTimeBuckets(
  nodes: StarMapNode[],
  bucketCount = 12
): TimeBucket[] {
  if (nodes.length === 0) {
    return [];
  }

  let minTime = nodes[0].createdAt;
  let maxTime = nodes[0].createdAt;

  for (const node of nodes) {
    if (node.createdAt < minTime) {
      minTime = node.createdAt;
    }
    if (node.createdAt > maxTime) {
      maxTime = node.createdAt;
    }
  }

  const span = maxTime === minTime ? 1000 : maxTime - minTime;
  const bucketSize = span / bucketCount;

  const buckets: TimeBucket[] = [];
  for (let i = 0; i < bucketCount; i++) {
    const startTime = minTime + i * bucketSize;
    const endTime = i === bucketCount - 1 ? maxTime + 1 : startTime + bucketSize;

    const date = new Date(startTime);
    const label = `${date.getMonth() + 1}/${date.getDate()}`;

    buckets.push({
      bucketIndex: i,
      startTime,
      endTime,
      label,
      skillCount: 0,
      memoryCount: 0,
    });
  }

  for (const node of nodes) {
    const rel = node.createdAt - minTime;
    let idx = Math.floor(rel / bucketSize);
    if (idx < 0) {
      idx = 0;
    }
    if (idx >= bucketCount) {
      idx = bucketCount - 1;
    }

    if (node.type === 'skill') {
      buckets[idx].skillCount += 1;
    } else {
      buckets[idx].memoryCount += 1;
    }
  }

  return buckets;
}

export function getCutoffTimestamp(
  nodes: StarMapNode[],
  progress: number
): number {
  if (nodes.length === 0) {
    return Date.now();
  }

  let minTime = nodes[0].createdAt;
  let maxTime = nodes[0].createdAt;

  for (const node of nodes) {
    if (node.createdAt < minTime) {
      minTime = node.createdAt;
    }
    if (node.createdAt > maxTime) {
      maxTime = node.createdAt;
    }
  }

  const clamped = Math.max(0, Math.min(1, progress));
  return minTime + clamped * (maxTime - minTime);
}
