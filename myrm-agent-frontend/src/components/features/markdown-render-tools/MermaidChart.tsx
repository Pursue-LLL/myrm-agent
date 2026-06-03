'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useTheme } from 'next-themes';
import { useLazyMermaid } from '@/components/features/app-shell/lazy-mermaid';
import {
  ZoomInAreaIcon,
  ZoomOutAreaIcon,
  RefreshIcon,
  Maximize01Icon,
  Minimize01Icon,
  Loading01Icon,
  Copy01Icon,
  Tick01Icon,
  Download01Icon,
} from 'hugeicons-react';
import { useTranslations } from 'next-intl';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { buildMermaidConfig } from './mermaid-theme';
import type { MermaidChartProps, LegendItem } from './mermaid-theme';
import MermaidLegendPanel from './MermaidLegendPanel';

const MermaidChart: React.FC<MermaidChartProps> = ({ chart, id }) => {
  const t = useTranslations('mermaidChart');
  const { mermaidLib } = useLazyMermaid();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const elementRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const errorTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastChartRef = useRef<string>('');

  const [isInitialized, setIsInitialized] = useState(false);
  const [lastValidSvg, setLastValidSvg] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [showError, setShowError] = useState(false);
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

  const [copied, setCopied] = useState(false);
  const copiedTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [legends, setLegends] = useState<LegendItem[]>([]);
  const [activeLegends, setActiveLegends] = useState<Set<string>>(new Set());

  const handleCopySource = useCallback(async () => {
    if (!chart) return;
    const ok = await writeToClipboard(chart, true);
    if (ok) {
      setCopied(true);
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = setTimeout(() => setCopied(false), 1500);
    }
  }, [chart]);

  const handleDownloadSvg = useCallback(() => {
    if (!lastValidSvg) return;
    const blob = new Blob([lastValidSvg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mermaid-${Date.now()}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }, [lastValidSvg]);

  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.2, 3));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.2, 0.3));
  const handleReset = () => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  };
  const toggleFullscreen = () => {
    setIsFullscreen((prev) => !prev);
    if (!isFullscreen) handleReset();
  };

  useEffect(() => {
    if (!isFullscreen) return;
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && setIsFullscreen(false);
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [isFullscreen]);

  // 统一的拖拽处理逻辑
  const handlePointerStart = useCallback(
    (clientX: number, clientY: number) => {
      if (scale > 1) {
        setIsDragging(true);
        setDragStart({ x: clientX - translate.x, y: clientY - translate.y });
      }
    },
    [scale, translate],
  );

  const handlePointerMove = useCallback(
    (clientX: number, clientY: number) => {
      if (isDragging && scale > 1) {
        setTranslate({ x: clientX - dragStart.x, y: clientY - dragStart.y });
      }
    },
    [isDragging, scale, dragStart],
  );

  const handlePointerEnd = useCallback(() => setIsDragging(false), []);

  // 双击缩放
  const handleDoubleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (scale === 1) setScale(2);
    else handleReset();
  };

  // 错误处理辅助函数
  const clearErrorTimeout = useCallback(() => {
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
      errorTimeoutRef.current = null;
    }
  }, []);

  const setErrorWithDelay = useCallback(() => {
    if (!isStreaming) {
      errorTimeoutRef.current = setTimeout(() => setShowError(true), 1000);
    }
  }, [isStreaming]);

  // 解析图例
  useEffect(() => {
    if (!chart) return;
    const classDefRegex = /classDef\s+(\w+)\s+(.+?)(?:;|\n|$)/g;
    let match;
    const extractedLegends: LegendItem[] = [];
    while ((match = classDefRegex.exec(chart)) !== null) {
      const className = match[1];
      const styles = match[2];

      // 尝试提取颜色用于图例指示器
      const fillMatch = styles.match(/fill:([^,]+)/);
      const color = fillMatch ? fillMatch[1].trim() : undefined;

      extractedLegends.push({
        className,
        label: className,
        color,
      });
    }

    setLegends((prev) => {
      if (JSON.stringify(prev) !== JSON.stringify(extractedLegends)) {
        setActiveLegends(new Set()); // 重置过滤状态
        return extractedLegends;
      }
      return prev;
    });
  }, [chart]);

  // 切换图例激活状态
  const toggleLegend = useCallback((className: string) => {
    setActiveLegends((prev) => {
      const next = new Set(prev);
      if (next.has(className)) {
        next.delete(className);
      } else {
        next.add(className);
      }
      return next;
    });
  }, []);

  // 防抖渲染函数
  const debouncedRender = useCallback(
    async (chartContent: string) => {
      if (!isInitialized || !chartContent?.trim()) return;

      setIsRendering(true);
      setShowError(false);
      clearErrorTimeout();

      const chartId = id || `mermaid-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;

      try {
        const trimmedChart = chartContent.trim();
        if (!mermaidLib) return;

        const isValid = await mermaidLib.parse(trimmedChart);

        if (!isValid) {
          setErrorWithDelay();
          return;
        }

        const { svg } = await mermaidLib.render(chartId, trimmedChart);

        setLastValidSvg(svg);
        setIsStreaming(false);
      } catch {
        setErrorWithDelay();
        document.getElementById(`d${chartId}`)?.remove();
      } finally {
        setIsRendering(false);
      }
    },
    [isInitialized, id, mermaidLib, clearErrorTimeout, setErrorWithDelay],
  );

  // SVG 样式优化与节点过滤
  const optimizeSvgStyles = useCallback((svgElement: SVGElement) => {
    const viewBox = svgElement.getAttribute('viewBox');
    let width = 400;

    if (viewBox) {
      const [, , w] = viewBox.split(' ').map(Number);
      if (isFinite(w) && w > 0) width = w;
    }

    const maxWidth = Math.min(width, 600);
    const containerWidth = containerRef.current?.clientWidth || 600;
    const autoScale = Math.min(1, (containerWidth - 80) / maxWidth);

    Object.assign(svgElement.style, {
      width: `${maxWidth}px`,
      maxWidth: '100%',
      height: 'auto',
      display: 'block',
      margin: '0 auto',
      borderRadius: '12px',
      backgroundColor: 'transparent',
      filter: 'drop-shadow(0 4px 6px -1px rgb(0 0 0 / 0.1))',
    });

    // 移动端自适应
    if (window.innerWidth < 768 && isFinite(autoScale) && autoScale > 0) {
      svgElement.style.transform = `scale(${autoScale})`;
      svgElement.style.transformOrigin = 'center top';
    }
  }, []);

  // 应用节点过滤
  useEffect(() => {
    if (!elementRef.current) return;
    const svg = elementRef.current.querySelector('svg');
    if (!svg) return;

    const isFiltering = activeLegends.size > 0;

    // 过滤节点
    const nodes = svg.querySelectorAll('.node');
    nodes.forEach((node) => {
      let isActive = false;
      if (isFiltering) {
        activeLegends.forEach((activeClass) => {
          if (node.classList.contains(activeClass)) {
            isActive = true;
          }
        });
      } else {
        isActive = true;
      }

      const el = node as HTMLElement;
      el.style.opacity = isActive ? '1' : '0.15';
      el.style.transition = 'opacity 0.3s ease';
    });

    // 过滤连线 (如果正在过滤，降低所有连线的透明度以减少视觉噪音)
    const edges = svg.querySelectorAll('.edgePaths .edgePath, .edgeLabel');
    edges.forEach((edge) => {
      const el = edge as HTMLElement;
      el.style.opacity = isFiltering ? '0.15' : '1';
      el.style.transition = 'opacity 0.3s ease';
    });
  }, [activeLegends, lastValidSvg]);

  // Initialize mermaid and re-initialize on theme change; handle chart rendering with debounce
  const prevIsDarkRef = useRef(isDark);
  useEffect(() => {
    if (!mermaidLib) return;

    const themeChanged = prevIsDarkRef.current !== isDark;
    prevIsDarkRef.current = isDark;

    if (!isInitialized || themeChanged) {
      const config = buildMermaidConfig(isDark);
      mermaidLib.initialize(config);
      setIsInitialized(true);
    }

    if (!chart) return;

    const isStreamingInput = chart !== lastChartRef.current && chart.length > lastChartRef.current.length;
    if (isStreamingInput) {
      setIsStreaming(true);
      setShowError(false);
      clearErrorTimeout();
    }
    lastChartRef.current = chart;

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(
      () => {
        debouncedRender(chart);
      },
      isStreamingInput ? 300 : 100,
    );

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, [chart, isDark, mermaidLib, isInitialized, debouncedRender, clearErrorTimeout]);

  // SVG 渲染
  useEffect(() => {
    if (lastValidSvg && elementRef.current) {
      elementRef.current.innerHTML = lastValidSvg;
      const svgElement = elementRef.current.querySelector('svg');
      if (svgElement) optimizeSvgStyles(svgElement);
    }
  }, [lastValidSvg, optimizeSvgStyles]);

  // 控制按钮配置
  const controlButtons = [
    { icon: copied ? Tick01Icon : Copy01Icon, onClick: handleCopySource, disabled: !chart, title: t('copySource') },
    { icon: Download01Icon, onClick: handleDownloadSvg, disabled: !lastValidSvg, title: t('downloadSvg') },
    { icon: ZoomOutAreaIcon, onClick: handleZoomOut, disabled: scale <= 0.3, title: t('zoomOut') },
    { icon: ZoomInAreaIcon, onClick: handleZoomIn, disabled: scale >= 3, title: t('zoomIn') },
    { icon: RefreshIcon, onClick: handleReset, disabled: false, title: t('reset') },
    {
      icon: isFullscreen ? Minimize01Icon : Maximize01Icon,
      onClick: toggleFullscreen,
      disabled: false,
      title: isFullscreen ? t('exitFullscreen') : t('fullscreen'),
    },
  ];

  // 共享渲染片段（消除 normal/fullscreen 容器之间的 JSX 重复）
  const renderStatusIndicator = () =>
    (isStreaming || isRendering) && (
      <div className="absolute top-3 left-3 z-10 flex items-center space-x-2 px-3 py-1.5 bg-primary/10 dark:bg-primary/20 text-primary dark:text-primary text-xs rounded-lg backdrop-blur-sm border border-primary/20 dark:border-primary/30">
        <Loading01Icon size={12} className="animate-spin" />
        <span className="font-medium">{isRendering ? t('rendering') : t('receiving')}</span>
      </div>
    );

  const renderControlButtons = (alwaysVisible: boolean) => (
    <div
      className={`absolute top-3 right-3 z-10 flex space-x-1 ${alwaysVisible ? '' : 'opacity-0 group-hover:opacity-100'} transition-all duration-200`}
    >
      {controlButtons.map(({ icon: Icon, onClick, disabled, title }, index) => (
        <button
          key={index}
          onClick={onClick}
          disabled={disabled}
          className="p-2 bg-background/90 dark:bg-background/90 border border-border rounded-lg hover:bg-muted dark:hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 backdrop-blur-sm"
          title={title}
          aria-label={title}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  );

  const renderScaleIndicator = () =>
    scale !== 1 && (
      <div className="absolute top-3 left-3 z-10 px-3 py-1 bg-foreground/80 text-background text-xs rounded-lg font-medium backdrop-blur-sm">
        {Math.round(scale * 100)}%
      </div>
    );

  const dragHandlers = {
    onMouseDown: (e: React.MouseEvent) => handlePointerStart(e.clientX, e.clientY),
    onMouseMove: (e: React.MouseEvent) => handlePointerMove(e.clientX, e.clientY),
    onMouseUp: handlePointerEnd,
    onMouseLeave: handlePointerEnd,
    onTouchStart: (e: React.TouchEvent) =>
      e.touches.length === 1 && handlePointerStart(e.touches[0].clientX, e.touches[0].clientY),
    onTouchMove: (e: React.TouchEvent) =>
      e.touches.length === 1 && (e.preventDefault(), handlePointerMove(e.touches[0].clientX, e.touches[0].clientY)),
    onTouchEnd: handlePointerEnd,
    onDoubleClick: handleDoubleClick,
  };

  const dragCursorStyle = {
    cursor: scale > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default',
    touchAction: scale > 1 ? 'none' : 'auto',
  } as const;

  const renderPlaceholder = () =>
    !lastValidSvg &&
    !isRendering && (
      <div className="flex flex-col items-center justify-center text-muted-foreground py-12">
        <div className="text-sm mb-2 font-medium">{t('waitingContent')}</div>
        {chart && (
          <div className="text-xs text-muted-foreground max-w-md text-center bg-muted px-3 py-1 rounded-lg">
            {t('receiving')}: {chart.substring(0, 50)}
            {chart.length > 50 ? '...' : ''}
          </div>
        )}
      </div>
    );

  // 错误状态渲染
  if (showError && chart?.trim()) {
    return (
      <div className="border border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-700 rounded-xl p-4 my-4">
        <div className="flex items-center space-x-2">
          <div className="text-red-600 dark:text-red-400 font-medium">{t('syntaxError')}</div>
        </div>
        <div className="text-red-600 dark:text-red-400 text-sm mt-1">{t('syntaxErrorDesc')}</div>
        <details className="mt-2">
          <summary className="text-red-600 dark:text-red-400 text-sm cursor-pointer hover:underline">
            {t('viewOriginalCode')}
          </summary>
          <pre className="text-red-600 dark:text-red-400 text-xs mt-1 whitespace-pre-wrap bg-red-100 dark:bg-red-900/10 p-2 rounded">
            {chart}
          </pre>
        </details>
      </div>
    );
  }

  const normalContainer = (
    <div
      ref={containerRef}
      tabIndex={0}
      className="mermaid-container my-4 bg-secondary dark:bg-secondary rounded-xl border border-border relative group focus:outline-none focus:ring-2 focus:ring-ring/20 transition-all duration-200 hover:shadow-lg hover:shadow-muted/50"
    >
      {renderStatusIndicator()}
      {renderControlButtons(false)}
      {renderScaleIndicator()}
      <MermaidLegendPanel legends={legends} activeLegends={activeLegends} onToggleLegend={toggleLegend} />

      <div className="overflow-hidden p-4" {...dragHandlers} style={dragCursorStyle}>
        <div
          ref={elementRef}
          className="mermaid-chart flex justify-center items-center transition-transform duration-200 ease-out min-h-[120px]"
          style={{
            transform: `scale(${scale}) translate(${translate.x / scale}px, ${translate.y / scale}px)`,
            transformOrigin: 'center',
            maxWidth: '100%',
            width: '100%',
          }}
        >
          {renderPlaceholder()}
        </div>
      </div>

      <div className="absolute bottom-2 right-2 text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-background/90 dark:bg-background/90 px-2 py-1 rounded-full backdrop-blur-sm">
        {t('doubleClickZoom')}
      </div>
    </div>
  );

  const fullscreenContainer = (
    <div className="fixed inset-0 z-50 bg-secondary dark:bg-secondary w-screen h-screen overflow-hidden">
      {renderStatusIndicator()}
      {renderControlButtons(true)}
      {renderScaleIndicator()}
      <MermaidLegendPanel legends={legends} activeLegends={activeLegends} onToggleLegend={toggleLegend} />

      <div
        className="h-screen w-screen flex items-center justify-center p-8 overflow-hidden"
        {...dragHandlers}
        style={dragCursorStyle}
      >
        <div
          className="mermaid-chart flex justify-center items-center transition-transform duration-200 ease-out min-h-0"
          style={{
            transform: `scale(${scale}) translate(${translate.x / scale}px, ${translate.y / scale}px)`,
            transformOrigin: 'center',
            maxWidth: 'none',
            width: 'auto',
          }}
        >
          <div ref={isFullscreen ? elementRef : undefined}>
            {isFullscreen && lastValidSvg && <div dangerouslySetInnerHTML={{ __html: lastValidSvg }} />}
          </div>
          {renderPlaceholder()}
        </div>
      </div>
    </div>
  );

  // 使用 Portal 渲染全屏模式
  if (isFullscreen && typeof window !== 'undefined') {
    return (
      <>
        {normalContainer}
        {createPortal(fullscreenContainer, document.body)}
      </>
    );
  }

  return normalContainer;
};

export default MermaidChart;
