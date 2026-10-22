/**
 * [INPUT]
 * - dataDashboardTypes: InteractiveDashboardArtifactProps, DashboardSpec, KpiMetric
 * - dataDashboardUtils: parseDashboardSpec, generateStandaloneDashboardHtml
 *
 * [OUTPUT]
 * - InteractiveDashboardArtifact: High-fidelity reactive web dashboard artifact component
 *
 * [POS]
 * Interactive Web Dashboard Renderer for ZeroPromptAutonomousVisualizationAndDynamicWebDashboardEngine (Item 49 P1).
 * Strictly under 380 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useMemo, useCallback } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Download,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  Search,
  LayoutDashboard,
  BarChart2,
  LineChart,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { InteractiveDashboardArtifactProps } from './dataDashboardTypes';
import { parseDashboardSpec, generateStandaloneDashboardHtml } from './dataDashboardUtils';

export const InteractiveDashboardArtifact: React.FC<InteractiveDashboardArtifactProps> = memo(({
  content,
  title,
  className = '',
  onDownloadHtml,
}) => {
  const t = useTranslations('dataDashboard');
  const [searchTerm, setSearchTerm] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeChartMode, setActiveChartMode] = useState<'bar' | 'line'>('bar');

  const spec = useMemo(() => {
    return parseDashboardSpec(content, title);
  }, [content, title]);

  const primaryTable = spec.tables.length > 0 ? spec.tables[0] : null;

  const filteredRows = useMemo(() => {
    if (!primaryTable) {
      return [];
    }
    if (!searchTerm.trim()) {
      return primaryTable.rows;
    }
    const lower = searchTerm.toLowerCase();
    return primaryTable.rows.filter((row) => {
      return row.some((cell) => cell.toLowerCase().includes(lower));
    });
  }, [primaryTable, searchTerm]);

  const handleDownloadStandalone = useCallback(() => {
    const htmlString = generateStandaloneDashboardHtml(spec);
    const blob = new Blob([htmlString], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${spec.title || 'dashboard'}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    if (onDownloadHtml) {
      onDownloadHtml();
    }
  }, [spec, onDownloadHtml]);

  const handleCopySummary = useCallback(async () => {
    const kpiSummary = spec.kpis.map((k) => `${k.label}: ${k.value} (${k.detail || ''})`).join('\n');
    const text = `# ${spec.title}\n${spec.subtitle || ''}\n\n[核心指标]\n${kpiSummary}`;
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  }, [spec]);

  return (
    <div
      data-testid="interactive-dashboard-artifact-root"
      className={`flex flex-col h-full w-full bg-slate-900 text-slate-100 overflow-y-auto select-text transition-all ${
        isFullscreen ? 'fixed inset-0 z-50 p-6 bg-slate-950' : 'p-4 rounded-xl border border-slate-800'
      } ${className}`}
    >
      {/* HUD Header Toolbar */}
      <header className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800 shrink-0 gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 shrink-0">
            <LayoutDashboard className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-slate-100 truncate" title={spec.title}>
              {spec.title}
            </h2>
            <p className="text-xs text-slate-400 truncate mt-0.5">
              {spec.subtitle || t('defaultSubtitle')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            data-testid="copy-dashboard-btn"
            onClick={handleCopySummary}
            title={t('copySummary')}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>

          <button
            type="button"
            data-testid="download-html-btn"
            onClick={handleDownloadStandalone}
            title={t('downloadStandaloneHtml')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors shadow-xs"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{t('exportHtml')}</span>
          </button>

          <button
            type="button"
            data-testid="fullscreen-toggle-btn"
            onClick={() => {
              setIsFullscreen(!isFullscreen);
            }}
            title={isFullscreen ? t('exitFullscreen') : t('enterFullscreen')}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* KPI Metric Cards Grid */}
      {spec.kpis.length > 0 && (
        <section data-testid="kpi-grid" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
          {spec.kpis.map((kpi, idx) => {
            const isUp = kpi.trend === 'up';
            const isDown = kpi.trend === 'down';
            return (
              <div
                key={`${kpi.label}_${idx}`}
                data-testid={`kpi-card-${idx}`}
                className="p-4 rounded-xl bg-slate-800/80 border border-slate-700/60 shadow-xs flex flex-col gap-1.5"
              >
                <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
                  <span className="truncate">{kpi.label}</span>
                  {isUp && <TrendingUp className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                  {isDown && <TrendingDown className="w-3.5 h-3.5 text-rose-400 shrink-0" />}
                  {!isUp && !isDown && <Minus className="w-3.5 h-3.5 text-slate-500 shrink-0" />}
                </div>

                <div className="text-xl font-bold font-mono tracking-tight text-blue-400">
                  {kpi.value}
                </div>

                {kpi.detail && (
                  <div className={`text-[11px] truncate ${isUp ? 'text-emerald-400' : isDown ? 'text-rose-400' : 'text-slate-400'}`}>
                    {kpi.detail}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}

      {/* Dynamic Visual Chart Stage */}
      {spec.charts.length > 0 && (
        <section data-testid="chart-stage" className="mb-5 p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">
                {spec.charts[0].title}
              </h3>
              {spec.charts[0].description && (
                <p className="text-xs text-slate-400 mt-0.5">
                  {spec.charts[0].description}
                </p>
              )}
            </div>

            <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-lg border border-slate-700/60">
              <button
                type="button"
                data-testid="chart-mode-bar-btn"
                onClick={() => {
                  setActiveChartMode('bar');
                }}
                className={`p-1 rounded ${activeChartMode === 'bar' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                title="柱状图"
              >
                <BarChart2 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                data-testid="chart-mode-line-btn"
                onClick={() => {
                  setActiveChartMode('line');
                }}
                className={`p-1 rounded ${activeChartMode === 'line' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                title="折线图"
              >
                <LineChart className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Inline SVG Chart Body */}
          <div data-testid="chart-svg-container" className="h-44 w-full flex items-end pt-4 pb-2">
            {(() => {
              const series = spec.charts[0].series[0];
              if (!series || series.data.length === 0) {
                return <div className="text-xs text-slate-500 m-auto">{t('noChartData')}</div>;
              }
              const maxVal = Math.max(...series.data, 1);
              const dataPoints = series.data;
              const xLabels = spec.charts[0].x_axis_labels;

              if (activeChartMode === 'line') {
                const width = 500;
                const height = 150;
                const padding = 20;
                const points = dataPoints.map((val, i) => {
                  const x = padding + (i / Math.max(dataPoints.length - 1, 1)) * (width - 2 * padding);
                  const y = height - padding - (val / maxVal) * (height - 2 * padding);
                  return `${x.toFixed(1)},${y.toFixed(1)}`;
                }).join(' ');

                return (
                  <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
                    <polyline
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      points={points}
                    />
                    {dataPoints.map((val, i) => {
                      const x = padding + (i / Math.max(dataPoints.length - 1, 1)) * (width - 2 * padding);
                      const y = height - padding - (val / maxVal) * (height - 2 * padding);
                      return (
                        <circle key={`dot_${i}`} cx={x} cy={y} r="3.5" fill="#38bdf8" className="transition-all hover:r-5" />
                      );
                    })}
                  </svg>
                );
              }

              return (
                <div className="w-full h-full flex items-end gap-2 px-2">
                  {dataPoints.map((val, i) => {
                    const heightPct = Math.max((val / maxVal) * 100, 4);
                    return (
                      <div key={`bar_${i}`} className="flex-1 flex flex-col items-center gap-1 group">
                        <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">
                          {val}
                        </span>
                        <div
                          style={{ height: `${heightPct}%` }}
                          className="w-full bg-blue-500 hover:bg-blue-400 rounded-t transition-all shadow-xs"
                        />
                        <span className="text-[10px] text-slate-400 truncate w-full text-center">
                          {xLabels[i] || `#${i + 1}`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>
        </section>
      )}

      {/* Perspective Table Section */}
      {primaryTable && (
        <section data-testid="table-section" className="flex-1 flex flex-col rounded-xl bg-slate-800/60 border border-slate-700/60 overflow-hidden">
          <div className="p-3.5 border-b border-slate-700/60 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-200">
                {primaryTable.title || t('detailTableTitle')}
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-700 text-slate-300 font-mono">
                {filteredRows.length} {t('rowsCount')}
              </span>
            </div>

            <div className="relative max-w-xs w-48">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400 pointer-events-none" />
              <input
                type="text"
                data-testid="table-search-input"
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                }}
                placeholder={t('searchPlaceholder')}
                className="w-full pl-8 pr-3 py-1 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
          </div>

          <div className="flex-1 overflow-x-auto overflow-y-auto max-h-80">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-800/80 sticky top-0 border-b border-slate-700 text-slate-400 font-medium">
                  {primaryTable.headers.map((h, i) => (
                    <th key={`th_${i}`} className="p-2.5 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-750">
                {filteredRows.map((row, rIdx) => (
                  <tr key={`tr_${rIdx}`} className="hover:bg-slate-750/50 transition-colors text-slate-300">
                    {row.map((cell, cIdx) => (
                      <td key={`td_${rIdx}_${cIdx}`} className="p-2.5 truncate max-w-xs">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
});

InteractiveDashboardArtifact.displayName = 'InteractiveDashboardArtifact';
