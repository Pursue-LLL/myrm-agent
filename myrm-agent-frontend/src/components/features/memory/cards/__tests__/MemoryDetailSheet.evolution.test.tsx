/** @vitest-environment jsdom */
/**
 * MemoryDetailSheet 演变历史（EvolutionHistory + 纠正链）单测。
 *
 * 覆盖：
 * - parseMergeHistory 三段式解析（timestamp|action|summary）
 * - 详情 Sheet 打开时渲染演变历史时间线（mergeCount 徽标 + 动作标签）
 * - correction_of 纠正链条目
 * - 无演变数据时不渲染
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values && 'count' in values) {
    return `${key} ${values.count}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('../MemoryTypeIcon', () => ({
  default: () => null,
}));

import MemoryDetailSheet, { parseMergeHistory } from '../MemoryDetailSheet';
import type { Memory } from '@/store/memory';

function renderSheet(memory: Partial<Memory>) {
  return render(<MemoryDetailSheet memory={memory as Memory} open onOpenChange={() => {}} />);
}

describe('parseMergeHistory', () => {
  it('parses timestamp|action|summary lines', () => {
    const entries = parseMergeHistory('09-12 10:00|MERGE|prefers dark mode\n09-13 18:30|REPLACE|moved to global');
    expect(entries).toEqual([
      { timestamp: '09-12 10:00', action: 'MERGE', summary: 'prefers dark mode' },
      { timestamp: '09-13 18:30', action: 'REPLACE', summary: 'moved to global' },
    ]);
  });

  it('returns empty array for empty or undefined input', () => {
    expect(parseMergeHistory(undefined)).toEqual([]);
    expect(parseMergeHistory('')).toEqual([]);
  });

  it('keeps pipes inside summary text', () => {
    const entries = parseMergeHistory('09-12 10:00|MERGE|a|b');
    expect(entries[0]?.summary).toBe('a|b');
  });
});

describe('MemoryDetailSheet evolution rendering', () => {
  it('renders evolution timeline with merge badge and action labels', () => {
    renderSheet({
      id: 'm1',
      memory_type: 'semantic',
      content: 'user prefers dark mode',
      merge_count: 2,
      merge_history: '09-12 10:00|MERGE|prefers dark mode\n09-13 18:30|REPLACE|moved to global',
    } as Memory);

    expect(screen.getByText('fields.evolutionHistory')).toBeInTheDocument();
    // mergeCount 徽标：stableT 对带 count 的 key 返回 "key count"
    expect(screen.getByText('fields.mergeCount 2')).toBeInTheDocument();
    expect(screen.getByText('fields.merged')).toBeInTheDocument();
    expect(screen.getByText('fields.replaced')).toBeInTheDocument();
    expect(screen.getByText('moved to global')).toBeInTheDocument();
  });

  it('renders correction chain entry for correction_of', () => {
    renderSheet({
      id: 'm2',
      memory_type: 'semantic',
      content: 'corrected fact',
      correction_of: 'abcdef1234567890',
    } as Memory);

    expect(screen.getByText('fields.corrects')).toBeInTheDocument();
    expect(screen.getByText('abcdef12')).toBeInTheDocument();
  });

  it('renders neither block without merge history or correction', () => {
    renderSheet({
      id: 'm3',
      memory_type: 'semantic',
      content: 'plain fact',
    } as Memory);

    expect(screen.queryByText('fields.evolutionHistory')).not.toBeInTheDocument();
    expect(screen.queryByText('fields.corrects')).not.toBeInTheDocument();
  });

  it('does not mutate the memory object passed in', () => {
    const memory = {
      id: 'm4',
      memory_type: 'semantic',
      content: 'no mutation case',
      merge_count: 1,
      merge_history: '09-12 10:00|MERGE|x',
    } as Memory;
    renderSheet(memory);
    expect(memory.merge_history).toContain('MERGE');
  });

  it('renders source evidence quote snippet block', () => {
    renderSheet({
      id: 'm5',
      memory_type: 'semantic',
      content: 'fact with evidence',
      metadata: { quote_snippet: '用户原话引用片段' },
    } as Memory);

    expect(screen.getByText('sourceEvidence')).toBeInTheDocument();
    expect(screen.getByText('「用户原话引用片段」')).toBeInTheDocument();
  });

  it('renders the source evidence quote block with evolution history', () => {
    renderSheet({
      id: 'm5',
      memory_type: 'semantic',
      content: 'fact with evidence',
      metadata: { quote_snippet: 'I prefer dark mode' },
      merge_history: '09-12 10:00|MERGE|dark mode noted',
    } as Memory);

    expect(screen.getByText('sourceEvidence')).toBeInTheDocument();
    expect(screen.getByText(/「I prefer dark mode」/)).toBeInTheDocument();
    expect(screen.getByText('fields.evolutionHistory')).toBeInTheDocument();
  });
});