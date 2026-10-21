import {
  StarMapFilter,
  StarMapLink,
  StarMapNode,
} from './starMapTypes';

const NOW = Date.now();
const DAY_MS = 24 * 3600 * 1000;

export const INITIAL_STAR_MAP_NODES: StarMapNode[] = [
  // 核心技能节点（金星 Gold Stars）
  {
    id: 'skill-ts-clean-arch',
    type: 'skill',
    name: 'TypeScript Clean Architecture 审查',
    summary: '自动审查前端分层契约，杜绝循环依赖与 Any 渗透',
    createdAt: NOW - 25 * DAY_MS,
    recallCount: 38,
    sourceChatId: 'chat-sess-1029',
    scope: 'global',
    evolutionCount: 3,
    tags: ['架构规范', 'TypeScript', '质量门禁'],
  },
  {
    id: 'skill-rust-zerocopy',
    type: 'skill',
    name: 'Rust 内存映射与零拷贝流',
    summary: '针对大文件与流式日志的高效处理例程',
    createdAt: NOW - 18 * DAY_MS,
    recallCount: 14,
    sourceChatId: 'chat-sess-2041',
    scope: 'agent-specific',
    agentId: 'agent-backend-dev',
    evolutionCount: 2,
    tags: ['Rust', '高性能', '内存映射'],
  },
  {
    id: 'skill-vitest-a11y',
    type: 'skill',
    name: 'WCAG 语义化与 a11y 自动化断言',
    summary: '检测无障碍焦点陷阱、dialog open 标签与 ARIA 规范',
    createdAt: NOW - 10 * DAY_MS,
    recallCount: 22,
    sourceChatId: 'chat-sess-3088',
    scope: 'global',
    evolutionCount: 1,
    tags: ['无障碍', 'Vitest', '前端测试'],
  },
  {
    id: 'skill-epoll-tuning',
    type: 'skill',
    name: 'Linux epoll 边缘触发网络调优',
    summary: '长连接高并发下的非阻塞套接字事件循环模式',
    createdAt: NOW - 3 * DAY_MS,
    recallCount: 6,
    sourceChatId: 'chat-sess-4112',
    scope: 'agent-specific',
    agentId: 'agent-infra',
    evolutionCount: 1,
    tags: ['Linux', '网络', '系统底层'],
  },

  // 记忆条目节点（蓝钻 Blue Diamonds）
  {
    id: 'mem-user-perf-priority',
    type: 'memory',
    name: '用户偏好：极度重视内存与防卡顿',
    summary: '用户电脑性能较弱，优先采用低损耗运算与流式处理',
    createdAt: NOW - 28 * DAY_MS,
    recallCount: 52,
    sourceChatId: 'chat-sess-0012',
    scope: 'global',
    tags: ['用户偏好', '性能红线'],
  },
  {
    id: 'mem-no-native-emoji',
    type: 'memory',
    name: '设计规范：严禁原生 Emoji',
    summary: '全站一律采用 Lucide 矢量图标，保持现代科技质感',
    createdAt: NOW - 20 * DAY_MS,
    recallCount: 45,
    sourceChatId: 'chat-sess-1029',
    scope: 'global',
    tags: ['UI规范', 'Lucide'],
  },
  {
    id: 'mem-dialog-open-a11y',
    type: 'memory',
    name: '技术踩坑：必须采用原生 dialog open',
    summary: '避免非交互 div 挂 onClick 触发 oxlint 与 a11y 警告',
    createdAt: NOW - 12 * DAY_MS,
    recallCount: 19,
    sourceChatId: 'chat-sess-3088',
    scope: 'global',
    tags: ['踩坑沉淀', 'a11y'],
  },
  {
    id: 'mem-submodule-commit',
    type: 'memory',
    name: '部署工程：myrm-agent 为独立子模块',
    summary: '所有前端组件改动必须在 myrm-agent 目录内完成提交与推送',
    createdAt: NOW - 5 * DAY_MS,
    recallCount: 28,
    sourceChatId: 'chat-sess-3990',
    scope: 'agent-specific',
    agentId: 'agent-infra',
    tags: ['工程规范', 'Git Submodule'],
  },
  {
    id: 'mem-epoll-starvation',
    type: 'memory',
    name: '故障经验：EPOLLET 惊群与饥饿防御',
    summary: '多线程唤醒时需配合 accept4 与非阻塞批量读取',
    createdAt: NOW - 2 * DAY_MS,
    recallCount: 4,
    sourceChatId: 'chat-sess-4112',
    scope: 'agent-specific',
    agentId: 'agent-infra',
    tags: ['故障复盘', '并发'],
  },
];

export const INITIAL_STAR_MAP_LINKS: StarMapLink[] = [
  {
    id: 'link-1',
    sourceId: 'mem-no-native-emoji',
    targetId: 'skill-ts-clean-arch',
    relation: 'chat-source',
    strength: 0.8,
  },
  {
    id: 'link-2',
    sourceId: 'skill-ts-clean-arch',
    targetId: 'skill-vitest-a11y',
    relation: 'evolution',
    strength: 0.9,
  },
  {
    id: 'link-3',
    sourceId: 'mem-dialog-open-a11y',
    targetId: 'skill-vitest-a11y',
    relation: 'chat-source',
    strength: 0.95,
  },
  {
    id: 'link-4',
    sourceId: 'skill-rust-zerocopy',
    targetId: 'skill-epoll-tuning',
    relation: 'evolution',
    strength: 0.75,
  },
  {
    id: 'link-5',
    sourceId: 'mem-epoll-starvation',
    targetId: 'skill-epoll-tuning',
    relation: 'chat-source',
    strength: 0.85,
  },
  {
    id: 'link-6',
    sourceId: 'mem-user-perf-priority',
    targetId: 'skill-rust-zerocopy',
    relation: 'co-occurrence',
    strength: 0.6,
  },
];

export function filterStarMapNodes(
  nodes: StarMapNode[],
  filter: StarMapFilter,
  now = Date.now()
): StarMapNode[] {
  return nodes.filter((node) => {
    // 范围过滤
    if (filter.scope === 'used' && node.recallCount === 0) {
      return false;
    }
    if (filter.scope === 'learned') {
      const isLearnedSkill = (node.evolutionCount ?? 0) > 0;
      const isLearnedMemory = node.type === 'memory';
      if (!isLearnedSkill && !isLearnedMemory) {
        return false;
      }
    }

    // 实体类型过滤
    if (filter.type !== 'all' && node.type !== filter.type) {
      return false;
    }

    // 作用域过滤（全局共享 vs 智能体专属）
    if (filter.agentScope !== 'all' && node.scope !== filter.agentScope) {
      return false;
    }

    // 时间窗口过滤
    if (filter.timeSpan !== 'all') {
      const days =
        filter.timeSpan === '7d' ? 7 : filter.timeSpan === '30d' ? 30 : 90;
      const cutoff = now - days * DAY_MS;
      if (node.createdAt < cutoff) {
        return false;
      }
    }

    return true;
  });
}

export function filterStarMapLinks(
  links: StarMapLink[],
  visibleNodeIds: Set<string>
): StarMapLink[] {
  return links.filter(
    (link) => visibleNodeIds.has(link.sourceId) && visibleNodeIds.has(link.targetId)
  );
}
