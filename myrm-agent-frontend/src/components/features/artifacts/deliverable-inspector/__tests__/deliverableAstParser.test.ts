import { describe, it, expect } from 'vitest';
import {
  parseDeliverableNodes,
  applySelectiveNodePatch,
  computeSnapshotDiff,
} from '../deliverableAstParser';
import type { DeliverableNode } from '../deliverableInspectorTypes';

describe('deliverableAstParser', () => {
  it('handles empty content gracefully', () => {
    const nodes = parseDeliverableNodes('', 'slides');
    expect(nodes).toEqual([]);
  });

  it('parses multi-slide presentation content into individual slide nodes', () => {
    const rawSlides = `
# 标题页：2026 战略规划
欢迎参会

---
## 第二页：核心数据指标
- 营收同比增长 150%
- 用户活跃度创历史新高

---
## 第三页：下一步行动路线
- Q1 启动产品自进化
- Q2 推进多端网关
    `.trim();

    const nodes = parseDeliverableNodes(rawSlides, 'slides');
    expect(nodes).toHaveLength(3);
    expect(nodes[0]?.title).toBe('标题页：2026 战略规划');
    expect(nodes[0]?.nodeType).toBe('slide');
    expect(nodes[1]?.title).toBe('第二页：核心数据指标');
    expect(nodes[2]?.title).toBe('第三页：下一步行动路线');
  });

  it('parses document markdown into section nodes', () => {
    const rawDoc = `
# 概述与架构背景
这是引言部分。

## 模块解耦方案
具体解耦逻辑如下。

## 门禁验证与交付
全量单测覆盖。
    `.trim();

    const nodes = parseDeliverableNodes(rawDoc, 'document');
    expect(nodes.length).toBeGreaterThanOrEqual(2);
    expect(nodes[0]?.nodeType).toBe('section');
  });

  it('parses spreadsheet into sheet nodes', () => {
    const rawSheet = `
### Sheet: 财务汇总
| 科目 | 金额 |
| 收入 | 1000 |

### Sheet: 成本明细
| 项目 | 支出 |
| 人力 | 600 |
    `.trim();

    const nodes = parseDeliverableNodes(rawSheet, 'spreadsheet');
    expect(nodes).toHaveLength(2);
    expect(nodes[0]?.nodeType).toBe('sheet');
    expect(nodes[0]?.title).toContain('财务汇总');
    expect(nodes[1]?.title).toContain('成本明细');
  });

  it('applies selective patch only to targeted node while preserving all others untouched', () => {
    const initialNodes: DeliverableNode[] = [
      { id: 'slide-1', index: 1, title: 'Slide 1', summary: 'S1', nodeType: 'slide', content: 'C1' },
      { id: 'slide-2', index: 2, title: 'Slide 2', summary: 'S2', nodeType: 'slide', content: 'C2' },
      { id: 'slide-3', index: 3, title: 'Slide 3', summary: 'S3', nodeType: 'slide', content: 'C3' },
    ];

    const patchedNodes = applySelectiveNodePatch(
      initialNodes,
      'slide-2',
      '## Slide 2 Updated\n新图表与更新数据',
      'Slide 2 Updated',
    );

    expect(patchedNodes[0]?.content).toBe('C1');
    expect(patchedNodes[1]?.title).toBe('Slide 2 Updated');
    expect(patchedNodes[1]?.content).toContain('新图表与更新数据');
    expect(patchedNodes[2]?.content).toBe('C3');
    expect(patchedNodes[1]?.metadata?.lastPatchedAt).toBeDefined();
  });

  it('computes accurate snapshot diffs between versions', () => {
    const beforeNodes: DeliverableNode[] = [
      { id: 'n-1', index: 1, title: 'Node 1', summary: 'S1', nodeType: 'section', content: 'Old Content' },
      { id: 'n-2', index: 2, title: 'Node 2', summary: 'S2', nodeType: 'section', content: 'Same Content' },
      { id: 'n-3', index: 3, title: 'Node 3', summary: 'S3', nodeType: 'section', content: 'Will be deleted' },
    ];

    const afterNodes: DeliverableNode[] = [
      { id: 'n-1', index: 1, title: 'Node 1', summary: 'S1', nodeType: 'section', content: 'New Content' },
      { id: 'n-2', index: 2, title: 'Node 2', summary: 'S2', nodeType: 'section', content: 'Same Content' },
      { id: 'n-4', index: 4, title: 'Node 4', summary: 'S4', nodeType: 'section', content: 'Newly added' },
    ];

    const diffs = computeSnapshotDiff(beforeNodes, afterNodes);
    expect(diffs).toHaveLength(4);

    const modDiff = diffs.find((d) => d.nodeId === 'n-1');
    expect(modDiff?.status).toBe('modified');

    const sameDiff = diffs.find((d) => d.nodeId === 'n-2');
    expect(sameDiff?.status).toBe('unchanged');

    const addDiff = diffs.find((d) => d.nodeId === 'n-4');
    expect(addDiff?.status).toBe('added');

    const delDiff = diffs.find((d) => d.nodeId === 'n-3');
    expect(delDiff?.status).toBe('removed');
  });
});
