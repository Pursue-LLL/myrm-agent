import { describe, it, expect } from 'vitest';
import { parseDashboardSpec, generateStandaloneDashboardHtml } from '../dataDashboardUtils';
import type { DashboardSpec } from '../dataDashboardTypes';

describe('dataDashboardUtils', () => {
  it('parses valid JSON content into DashboardSpec', () => {
    const jsonContent = JSON.stringify({
      title: 'Q3 财务监控大盘',
      subtitle: '财务与经营指标概览',
      kpis: [
        { label: '净利润', value: '¥1,250,000', change_pct: 12.5, trend: 'up' },
        { label: '运营成本', value: '¥420,000', change_pct: -3.2, trend: 'down' },
      ],
      charts: [
        {
          id: 'c1',
          title: '收入与利润走势',
          chart_type: 'bar',
          x_axis_labels: ['7月', '8月', '9月'],
          series: [{ name: '利润', data: [380000, 420000, 450000] }],
        },
      ],
      tables: [
        {
          title: '月度明细',
          headers: ['月份', '收入', '成本', '利润'],
          rows: [
            ['7月', '800000', '420000', '380000'],
            ['8月', '850000', '430000', '420000'],
          ],
        },
      ],
    });

    const spec = parseDashboardSpec(jsonContent, '默认标题');
    expect(spec.title).toBe('Q3 财务监控大盘');
    expect(spec.kpis.length).toBe(2);
    expect(spec.kpis[0].label).toBe('净利润');
    expect(spec.charts.length).toBe(1);
    expect(spec.tables.length).toBe(1);
    expect(spec.tables[0].rows.length).toBe(2);
  });

  it('infers KPIs, charts, and table from raw CSV text', () => {
    const csvContent = `月份,营收,获客数,留存率
2026-01,100000,500,82%
2026-02,120000,620,85%
2026-03,150000,780,88%`;

    const spec = parseDashboardSpec(csvContent, '获客经营看板');
    expect(spec.title).toBe('获客经营看板');
    expect(spec.kpis.length).toBeGreaterThan(1);
    expect(spec.kpis[0].label).toBe('总数据行数');
    expect(spec.kpis[0].value).toContain('3 条');

    // Revenue KPI
    const revenueKpi = spec.kpis.find((k) => k.label === '营收');
    expect(revenueKpi).toBeDefined();
    expect(revenueKpi?.trend).toBe('up');

    // Inferred Chart
    expect(spec.charts.length).toBeGreaterThan(0);
    expect(spec.charts[0].x_axis_labels).toEqual(['2026-01', '2026-02', '2026-03']);
    expect(spec.charts[0].series[0].data).toEqual([100000, 120000, 150000]);

    // Inferred Table
    expect(spec.tables.length).toBe(1);
    expect(spec.tables[0].headers).toEqual(['月份', '营收', '获客数', '留存率']);
    expect(spec.tables[0].rows.length).toBe(3);
  });

  it('safely handles non-structured plain text with baseline fallback', () => {
    const plainText = '这是一段简单的分析结论描述，没有包含任何表格和指标。';
    const spec = parseDashboardSpec(plainText, '文字摘要');
    expect(spec.title).toBe('文字摘要');
    expect(spec.kpis.length).toBe(1);
    expect(spec.kpis[0].label).toBe('内容大小');
    expect(spec.tables.length).toBe(1);
    expect(spec.tables[0].rows.length).toBe(1);
  });

  it('generates standalone HTML string with inline styles and table', () => {
    const sampleSpec: DashboardSpec = {
      title: '用户增长大盘',
      subtitle: '自主分析看板',
      kpis: [{ label: 'DAU', value: '45,200', trend: 'up', detail: '日环比 +4.5%' }],
      charts: [],
      tables: [
        {
          title: '渠道明细',
          headers: ['渠道', '新增'],
          rows: [
            ['自然搜索', '12000'],
            ['社交裂变', '8500'],
          ],
        },
      ],
      theme: 'modern_dark',
    };

    const html = generateStandaloneDashboardHtml(sampleSpec);
    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<title>用户增长大盘</title>');
    expect(html).toContain('DAU');
    expect(html).toContain('45,200');
    expect(html).toContain('自然搜索');
    expect(html).toContain('社交裂变');
  });
});
