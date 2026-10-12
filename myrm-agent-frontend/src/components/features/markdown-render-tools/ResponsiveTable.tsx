/**
 * ResponsiveTable - Markdown 表格响应式渲染与宿主 DOM 保留组件
 *
 * [POS]
 * ReactMarkdown 自定义 table 渲染器。
 * 1. 宿主 DOM 所有权保留与滚动锁定：流式追加 chunk 时保持 scrollLeft 稳定，杜绝视口跳动；
 * 2. 多列响应式折叠：>=4 列提供卡片/表格视图切换；
 * 3. 宽表格全景展开浮层：支持复杂超宽表格在独立 Lightbox 中沉浸式浏览；
 * 4. 零原生 emoji：全套标准 SVG 矢量图标。
 *
 * [INPUT]
 * MarkdownContent::components.table (POS: Markdown 渲染主组件，传入 children 与 isStreaming)
 *
 * [OUTPUT]
 * ResponsiveTable: 响应式 Markdown 表格组件（宿主 DOM 保留 + 滚动锁定 + Lightbox + Toggle）
 */

import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

const CARD_COLUMN_THRESHOLD = 4;

function TableGridIcon(): React.ReactElement {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="2" width="12" height="12" rx="2" />
      <path d="M2 6h12M2 10h12M6 2v12M10 2v12" />
    </svg>
  );
}

function CardListIcon(): React.ReactElement {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="2" width="12" height="5" rx="1.5" />
      <rect x="2" y="9" width="12" height="5" rx="1.5" />
    </svg>
  );
}

function ExpandLightboxIcon(): React.ReactElement {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M10 2h4v4M14 2L9 7M6 14H2v-4M2 14l5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CloseIcon(): React.ReactElement {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M3 3l10 10M13 3L3 13" strokeLinecap="round" />
    </svg>
  );
}

function getTextContent(node: React.ReactNode): string {
  if (typeof node === 'string') {
    return node;
  }
  if (typeof node === 'number') {
    return String(node);
  }
  if (!node) {
    return '';
  }
  if (Array.isArray(node)) {
    return node.map(getTextContent).join('');
  }
  if (React.isValidElement(node)) {
    const props = node.props as { children?: React.ReactNode };
    return getTextContent(props.children);
  }
  return '';
}

function flattenChildren(children: React.ReactNode): React.ReactElement[] {
  const result: React.ReactElement[] = [];
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) {
      return;
    }
    if (child.type === React.Fragment) {
      result.push(...flattenChildren((child.props as { children?: React.ReactNode }).children));
    } else {
      result.push(child);
    }
  });
  return result;
}

function extractHeaders(children: React.ReactNode): string[] {
  const headers: string[] = [];
  const topChildren = flattenChildren(children);
  const thead = topChildren.find((child) => typeof child.type === 'string' && child.type === 'thead');
  if (!thead) {
    return headers;
  }

  const theadChildren = flattenChildren((thead.props as { children?: React.ReactNode }).children);
  const tr = theadChildren.find((child) => typeof child.type === 'string' && child.type === 'tr');
  if (!tr) {
    return headers;
  }

  const ths = flattenChildren((tr.props as { children?: React.ReactNode }).children);
  for (const th of ths) {
    headers.push(getTextContent((th.props as { children?: React.ReactNode }).children));
  }
  return headers;
}

function hasComplexCells(children: React.ReactNode): boolean {
  let found = false;
  const check = (node: React.ReactNode) => {
    if (found) {
      return;
    }
    React.Children.forEach(node, (child) => {
      if (found || !React.isValidElement(child)) {
        return;
      }
      const props = child.props as Record<string, unknown>;
      if (
        typeof child.type === 'string' &&
        (child.type === 'td' || child.type === 'th') &&
        (props.colSpan || props.rowSpan || props.colspan || props.rowspan)
      ) {
        found = true;
        return;
      }
      check(props.children as React.ReactNode);
    });
  };
  check(children);
  return found;
}

function injectDataLabels(children: React.ReactNode, headers: string[]): React.ReactNode {
  const elements = flattenChildren(children);
  return elements.map((child, idx) => {
    const props = child.props as Record<string, unknown>;
    const type = child.type;

    if (typeof type === 'string' && type === 'tbody') {
      return React.cloneElement(child, {
        key: `tbody-${idx}`,
        ...props,
        children: injectDataLabels(props.children as React.ReactNode, headers),
      } as React.HTMLAttributes<HTMLElement>);
    }

    if (typeof type === 'string' && type === 'tr') {
      let cellIndex = 0;
      const cells = flattenChildren(props.children as React.ReactNode);
      const newChildren = cells.map((td, ci) => {
        const tdType = td.type;
        if (typeof tdType === 'string' && tdType === 'td') {
          const label = headers[cellIndex] || `#${cellIndex + 1}`;
          cellIndex++;
          return React.cloneElement(td, {
            key: `td-${ci}`,
            ...(td.props as Record<string, unknown>),
            'data-label': label,
          } as React.TdHTMLAttributes<HTMLTableCellElement>);
        }
        return td;
      });
      return React.cloneElement(child, {
        key: `tr-${idx}`,
        ...props,
        children: newChildren,
      } as React.HTMLAttributes<HTMLElement>);
    }

    return child;
  });
}

type ResponsiveTableProps = {
  children?: React.ReactNode;
  isStreaming?: boolean;
};

const ResponsiveTable = React.memo(({ children, isStreaming }: ResponsiveTableProps) => {
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card');
  const [isLightboxOpen, setIsLightboxOpen] = useState<boolean>(false);
  const t = useTranslations('MarkdownTable');

  const wrapperRef = useRef<HTMLDivElement>(null);
  const scrollLeftRef = useRef<number>(0);
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Preserve horizontal scroll position across streaming chunk re-renders
  useLayoutEffect(() => {
    if (wrapperRef.current && scrollLeftRef.current > 0) {
      wrapperRef.current.scrollLeft = scrollLeftRef.current;
    }
  }, [children]);

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (isLightboxOpen) {
      if (typeof dialog.showModal === 'function' && !dialog.open) {
        dialog.showModal();
      } else if (!dialog.open) {
        dialog.setAttribute('open', '');
      }
    } else {
      if (typeof dialog.close === 'function' && dialog.open) {
        dialog.close();
      } else if (dialog.open) {
        dialog.removeAttribute('open');
      }
    }
  }, [isLightboxOpen]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    scrollLeftRef.current = e.currentTarget.scrollLeft;
  }, []);

  const headers = useMemo(() => extractHeaders(children), [children]);
  const isComplex = useMemo(() => hasComplexCells(children), [children]);
  const enableCards = headers.length >= CARD_COLUMN_THRESHOLD && !isComplex && !isStreaming;

  const tableChildren = useMemo(() => {
    if (!enableCards || viewMode === 'table') {
      return children;
    }
    return injectDataLabels(children, headers);
  }, [children, enableCards, viewMode, headers]);

  const wrapperClass =
    enableCards && viewMode === 'card' ? 'responsive-table-wrapper responsive-table-cards' : 'responsive-table-wrapper';

  return (
    <div className="not-prose my-3">
      {enableCards && (
        <div className="responsive-table-toolbar flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="responsive-table-toggle inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-border/60 bg-muted/30 hover:bg-muted/60 transition-colors"
              onClick={() => setViewMode((v) => (v === 'card' ? 'table' : 'card'))}
              aria-label={viewMode === 'card' ? t('switchToTable') : t('switchToCard')}
              aria-pressed={viewMode === 'card'}
              title={viewMode === 'card' ? t('switchToTable') : t('switchToCard')}
            >
              {viewMode === 'card' ? (
                <>
                  <TableGridIcon />
                  <span>{t('tableView')}</span>
                </>
              ) : (
                <>
                  <CardListIcon />
                  <span>{t('cardView')}</span>
                </>
              )}
            </button>
          </div>

          <button
            type="button"
            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground rounded-md border border-border/40 hover:border-border transition-colors"
            onClick={() => setIsLightboxOpen(true)}
            aria-label="展开全景表格"
            title="展开全景表格"
          >
            <ExpandLightboxIcon />
            <span>全景</span>
          </button>
        </div>
      )}

      {/* Host table container with scroll retention */}
      <div
        ref={wrapperRef}
        className={wrapperClass}
        onScroll={handleScroll}
        data-streaming={isStreaming ? 'true' : undefined}
      >
        <table className="responsive-table">{tableChildren}</table>
      </div>

      {/* Wide Table Lightbox Dialog for multi-column inspection */}
      {isLightboxOpen && (
        <dialog
          ref={dialogRef}
          tabIndex={-1}
          aria-label="全景表格预览"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm m-0 w-full h-full max-w-none max-h-none border-none outline-none"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault();
              setIsLightboxOpen(false);
            }
          }}
        >
          <button
            type="button"
            className="fixed inset-0 -z-10 bg-transparent border-none cursor-default"
            onClick={() => setIsLightboxOpen(false)}
            aria-label="关闭预览背景"
            tabIndex={-1}
          />
          <div className="relative flex flex-col w-full max-w-6xl max-h-[85vh] bg-background border border-border rounded-xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-muted/20">
              <div className="flex items-center gap-2">
                <TableGridIcon />
                <h3 className="text-sm font-semibold text-foreground">全景表格视图</h3>
                <span className="text-xs text-muted-foreground px-2 py-0.5 rounded-full bg-muted/60">
                  {headers.length} 列
                </span>
              </div>
              <button
                type="button"
                onClick={() => setIsLightboxOpen(false)}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="关闭预览"
              >
                <CloseIcon />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 sm:p-6">
              <table className="responsive-table w-full">{children}</table>
            </div>
          </div>
        </dialog>
      )}
    </div>
  );
});

ResponsiveTable.displayName = 'ResponsiveTable';

export default ResponsiveTable;
