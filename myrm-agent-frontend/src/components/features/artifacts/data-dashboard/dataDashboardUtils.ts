/**
 * [INPUT]
 * - Raw string content (JSON or CSV)
 * - DashboardSpec object
 *
 * [OUTPUT]
 * - parseDashboardSpec: Robust parser returning normalized DashboardSpec
 * - generateStandaloneDashboardHtml: Generator producing single-file interactive HTML
 *
 * [POS]
 * Parsing and export utilities for ZeroPromptAutonomousVisualizationAndDynamicWebDashboardEngine (Item 49 P1).
 * Strictly under 240 lines. Zero `any`.
 */

import type {
  DashboardSpec,
  KpiMetric,
  ChartConfig,
  TableSpec,
  ChartSeries,
} from './dataDashboardTypes';

/**
 * Parse dashboard spec from raw string content (JSON or CSV).
 */
export function parseDashboardSpec(
  content: string,
  fallbackTitle = '业务数据看板',
): DashboardSpec {
  const trimmed = content.trim();

  // 1. Try parsing JSON format
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmed) as Partial<DashboardSpec>;
      if (Array.isArray(parsed.kpis) || Array.isArray(parsed.charts) || Array.isArray(parsed.tables)) {
        return {
          title: parsed.title || fallbackTitle,
          subtitle: parsed.subtitle || '由 Myrm 自主可视化引擎生成',
          kpis: parsed.kpis || [],
          charts: parsed.charts || [],
          tables: parsed.tables || [],
          theme: parsed.theme || 'modern_dark',
          timestamp: parsed.timestamp || Date.now(),
        };
      }
    } catch {
      // Fall through to CSV parsing
    }
  }

  // 2. Try parsing CSV format
  const lines = trimmed.split('\n').map((l) => l.trim()).filter((l) => l.length > 0);
  if (lines.length >= 2 && lines[0].includes(',')) {
    const headers = lines[0].split(',').map((h) => h.trim());
    const dataRows = lines.slice(1).map((line) => line.split(',').map((c) => c.trim()));

    // Infer numeric columns
    const numericIndices: number[] = [];
    headers.forEach((_, idx) => {
      const isNum = dataRows.every((row) => {
        if (!row[idx]) {
          return true;
        }
        const val = Number(row[idx].replace(/[¥$,%]/g, ''));
        return !Number.isNaN(val);
      });
      if (isNum) {
        numericIndices.push(idx);
      }
    });

    const kpis: KpiMetric[] = [
      {
        label: '总数据行数',
        value: `${dataRows.length} 条`,
        trend: 'neutral',
        detail: '样本全覆盖',
      },
    ];

    numericIndices.slice(0, 3).forEach((colIdx) => {
      const colName = headers[colIdx];
      const numbers = dataRows
        .map((r) => Number((r[colIdx] || '').replace(/[¥$,%]/g, '')))
        .filter((n) => !Number.isNaN(n));

      if (numbers.length > 0) {
        const sum = numbers.reduce((acc, v) => acc + v, 0);
        const first = numbers[0];
        const last = numbers[numbers.length - 1];
        const diff = first !== 0 ? ((last - first) / first) * 100 : 0;
        kpis.push({
          label: colName,
          value: Math.abs(sum) >= 1000 ? sum.toLocaleString() : sum.toFixed(2),
          change_pct: Number(diff.toFixed(1)),
          trend: diff > 0 ? 'up' : diff < 0 ? 'down' : 'neutral',
          detail: `首尾增幅: ${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`,
        });
      }
    });

    const charts: ChartConfig[] = [];
    if (numericIndices.length > 0) {
      const numIdx = numericIndices[0];
      const colName = headers[numIdx];
      const dataPoints = dataRows.slice(0, 10).map((r) => {
        return Number((r[numIdx] || '').replace(/[¥$,%]/g, '')) || 0;
      });
      const xLabels = dataRows.slice(0, 10).map((r, i) => r[0] || `#${i + 1}`);

      charts.push({
        id: `chart_${numIdx}`,
        title: `${colName} 分布与走势`,
        chart_type: 'bar',
        x_axis_labels: xLabels,
        series: [
          {
            name: colName,
            data: dataPoints,
          },
        ],
        description: '动态数据样本分布',
      });
    }

    const tableSpec: TableSpec = {
      title: fallbackTitle,
      headers,
      rows: dataRows,
      total_rows: dataRows.length,
    };

    return {
      title: fallbackTitle,
      subtitle: '自主从表格数据生成的交互看板',
      kpis,
      charts,
      tables: [tableSpec],
      theme: 'modern_dark',
      timestamp: Date.now(),
    };
  }

  // 3. Fallback baseline
  return {
    title: fallbackTitle,
    subtitle: '数据概要分析',
    kpis: [
      {
        label: '内容大小',
        value: `${content.length} 字符`,
        trend: 'neutral',
        detail: '文本预览模式',
      },
    ],
    charts: [],
    tables: [
      {
        title: '原始文本',
        headers: ['行号', '内容'],
        rows: lines.slice(0, 20).map((l, i) => [`${i + 1}`, l]),
        total_rows: lines.length,
      },
    ],
    theme: 'modern_dark',
    timestamp: Date.now(),
  };
}

/**
 * Generate a standalone, self-contained HTML dashboard string for offline inspection.
 */
export function generateStandaloneDashboardHtml(spec: DashboardSpec): string {
  const kpisHtml = spec.kpis
    .map(
      (k) => `
      <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;">
        <div style="font-size:12px;color:#94a3b8;">${k.label}</div>
        <div style="font-size:24px;font-weight:700;margin:6px 0;color:#38bdf8;">${k.value}</div>
        <div style="font-size:11px;color:${k.trend === 'up' ? '#34d399' : k.trend === 'down' ? '#f87171' : '#94a3b8'};">${k.detail || ''}</div>
      </div>
    `,
    )
    .join('');

  const tableHeaders = spec.tables.length > 0 ? spec.tables[0].headers.map((h) => `<th style="padding:10px;text-align:left;color:#94a3b8;border-bottom:1px solid #334155;">${h}</th>`).join('') : '';
  const tableRows = spec.tables.length > 0 ? spec.tables[0].rows.slice(0, 50).map((row) => `
    <tr>
      ${row.map((cell) => `<td style="padding:10px;border-bottom:1px solid #1e293b;color:#f8fafc;">${cell}</td>`).join('')}
    </tr>
  `).join('') : '';

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>${spec.title}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }
    h1 { font-size: 22px; margin-bottom: 4px; }
    p { font-size: 12px; color: #94a3b8; margin-bottom: 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .box { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 16px; overflow-x: auto; }
  </style>
</head>
<body>
  <h1>${spec.title}</h1>
  <p>${spec.subtitle || '由 Myrm 自主可视化引擎生成'}</p>
  <div class="grid">${kpisHtml}</div>
  <div class="box">
    <table>
      <thead><tr>${tableHeaders}</tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
  </div>
</body>
</html>`;
}
