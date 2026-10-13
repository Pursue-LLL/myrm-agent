/**
 * lazy-recharts 契约：recharts 用子元素的 `type.displayName || type.name` 识别 `Cell`，
 * 懒加载包装必须保留 `Cell` 这个名字，否则 Pie 扇区 / Bar 柱子的逐项颜色会被整体丢弃。
 * 不 mock recharts，直接断言真实渲染出的 SVG 填充色。
 */
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Bar, BarChart, Cell, Pie, PieChart } from '../lazy-recharts';

const COLORS = ['#e11d48', '#2563eb', '#059669'];
const ROWS = [
  { name: 'a', value: 3 },
  { name: 'b', value: 2 },
  { name: 'c', value: 1 },
];

function fillsOf(container: HTMLElement, selector: string): Array<string | null> {
  return Array.from(container.querySelectorAll(selector)).map((node) => node.getAttribute('fill'));
}

describe('lazy-recharts Cell', () => {
  it('keeps the per-slice colours of Cell children on a Pie', async () => {
    const { container } = render(
      <PieChart width={200} height={200}>
        <Pie data={ROWS} dataKey="value" nameKey="name" isAnimationActive={false}>
          {ROWS.map((row, index) => (
            <Cell key={row.name} fill={COLORS[index]} />
          ))}
        </Pie>
      </PieChart>,
    );

    await waitFor(() => expect(container.querySelectorAll('.recharts-sector')).toHaveLength(ROWS.length));
    expect(fillsOf(container, '.recharts-sector')).toEqual(COLORS);
  });

  it('keeps the per-bar colours of Cell children on a Bar', async () => {
    const { container } = render(
      <BarChart width={200} height={200} data={ROWS}>
        <Bar dataKey="value" isAnimationActive={false}>
          {ROWS.map((row, index) => (
            <Cell key={row.name} fill={COLORS[index]} />
          ))}
        </Bar>
      </BarChart>,
    );

    await waitFor(() => expect(container.querySelectorAll('.recharts-rectangle')).toHaveLength(ROWS.length));
    expect(fillsOf(container, '.recharts-rectangle')).toEqual(COLORS);
  });
});
