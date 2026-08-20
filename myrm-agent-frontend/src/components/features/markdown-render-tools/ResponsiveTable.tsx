/**
 * ResponsiveTable - Markdown 表格响应式渲染组件
 *
 * [POS]
 * ReactMarkdown 自定义 table 渲染器。所有表格 overflow-x-auto 防溢出；≥4列移动端自动转卡片视图。
 *
 * [INPUT]
 * MarkdownContent::components.table (POS: Markdown 渲染主组件，传入 children 与 isStreaming)
 *
 * [OUTPUT]
 * ResponsiveTable: 响应式 Markdown 表格组件（overflow 防溢出 + 多列卡片视图 + Toggle 切换）
 */
import React, { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

const CARD_COLUMN_THRESHOLD = 4;

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
  const t = useTranslations('MarkdownTable');

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
        <div className="responsive-table-toolbar">
          <button
            type="button"
            className="responsive-table-toggle"
            onClick={() => setViewMode((v) => (v === 'card' ? 'table' : 'card'))}
            aria-label={viewMode === 'card' ? t('switchToTable') : t('switchToCard')}
            aria-pressed={viewMode === 'card'}
            title={viewMode === 'card' ? t('switchToTable') : t('switchToCard')}
          >
            {viewMode === 'card' ? '▦ ' + t('tableView') : '▤ ' + t('cardView')}
          </button>
        </div>
      )}
      <div className={wrapperClass}>
        <table className="responsive-table">{tableChildren}</table>
      </div>
    </div>
  );
});

ResponsiveTable.displayName = 'ResponsiveTable';

export default ResponsiveTable;
