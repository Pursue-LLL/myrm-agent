'use client';

/**
 * [INPUT]
 * @/store/useResearchStore (POS: Research 工作台全局状态)
 * ./ResourcePoolPanel (POS: 左栏资料池)
 * ../chat-window/ChatWindow (POS: 聊天主组件)
 * ./ResearchOutputPanel (POS: 右栏工件输出面板)
 * ./useResearchSync (POS: 资料勾选 → mentionReferences 同步)
 *
 * [OUTPUT]
 * ResearchLayout: 三栏研究工作台布局容器
 *
 * [POS]
 * Research 三栏布局入口。容器宽度 ≥ 72rem 时三栏并列、分割线可拖拽；更窄时三栏仍全部挂载，只显示当前 Tab 的一栏。
 */

import { useCallback, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { BookOpen, MessageSquare, FileText, type LucideIcon } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { cn } from '@/lib/utils/classnameUtils';
import ResourcePoolPanel from './ResourcePoolPanel';
import useResearchStore from '@/store/useResearchStore';
import type { ResearchTab } from '@/store/useResearchStore';
import { useResearchSync } from './useResearchSync';

const ChatWindow = dynamic(() => import('../chat-window/ChatWindow'), { ssr: false });
const ResearchOutputPanel = dynamic(() => import('./ResearchOutputPanel'), { ssr: false });

const LEFT_MIN_WIDTH = 240;
const LEFT_MAX_WIDTH = 480;
const RIGHT_MIN_WIDTH = 280;
const RIGHT_MAX_WIDTH = 600;
const LEFT_DEFAULT_WIDTH = 300;
const RIGHT_DEFAULT_WIDTH = 380;
// The chat needs room for its composer toolbar, so neither dragging nor a shrinking window squeezes it below this.
// The `@6xl` (72rem) switch to three panes leaves it at least this much beside the default side panes.
const CENTER_MIN_WIDTH = 420;
const DRAG_HANDLES_WIDTH = 12;

const PANE_TABS = [
  { tab: 'resources', icon: BookOpen },
  { tab: 'chat', icon: MessageSquare },
  { tab: 'output', icon: FileText },
] as const satisfies ReadonlyArray<{ tab: ResearchTab; icon: LucideIcon }>;

const paneId = (tab: ResearchTab) => `research-pane-${tab}`;

/** Clamp a side pane to its own bounds without leaving the chat narrower than CENTER_MIN_WIDTH. */
function clampPaneWidth(width: number, min: number, max: number, otherPane: number, rowWidth: number): number {
  const roomForPane = rowWidth - otherPane - DRAG_HANDLES_WIDTH - CENTER_MIN_WIDTH;
  return Math.max(min, Math.min(max, roomForPane, width));
}

interface DragHandleProps {
  onDrag: (deltaX: number) => void;
}

function DragHandle({ onDrag }: DragHandleProps) {
  const isDragging = useRef(false);
  const lastX = useRef(0);

  const handlePointerDown = useCallback((e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    isDragging.current = true;
    lastX.current = e.clientX;
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!isDragging.current) {
        return;
      }
      const delta = e.clientX - lastX.current;
      lastX.current = e.clientX;
      onDrag(delta);
    },
    [onDrag],
  );

  const handlePointerUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  return (
    <div
      className="group hidden w-1.5 shrink-0 cursor-col-resize touch-none items-center justify-center transition-colors hover:bg-primary/10 @6xl:flex"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div className="h-8 w-0.5 rounded-full bg-border transition-colors group-hover:bg-primary/40" />
    </div>
  );
}

interface PaneProps {
  tab: ResearchTab;
  label: string;
  isActive: boolean;
  className?: string;
  children: ReactNode;
}

/**
 * One workbench pane. Narrow containers show only the active tab's pane; wide ones show all three side by side.
 * Layout containment makes the pane the containing block of everything inside it that is `position: fixed` (the chat's
 * composer dock, badges), so those stay within their pane instead of spanning the whole viewport.
 */
function Pane({ tab, label, isActive, className, children }: PaneProps) {
  return (
    <section
      id={paneId(tab)}
      aria-label={label}
      className={cn(
        'min-h-0 min-w-0 flex-1 overflow-hidden contain-layout @6xl:block',
        isActive ? 'block' : 'hidden',
        className,
      )}
    >
      {children}
    </section>
  );
}

export default function ResearchLayout() {
  const t = useTranslations('research');
  const { activeTab, setActiveTab } = useResearchStore();
  useResearchSync();

  const rowRef = useRef<HTMLDivElement>(null);
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT_WIDTH);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT_WIDTH);

  const handleLeftDrag = useCallback(
    (delta: number) => {
      const rowWidth = rowRef.current?.clientWidth ?? Number.POSITIVE_INFINITY;
      setLeftWidth((w) => clampPaneWidth(w + delta, LEFT_MIN_WIDTH, LEFT_MAX_WIDTH, rightWidth, rowWidth));
    },
    [rightWidth],
  );

  const handleRightDrag = useCallback(
    (delta: number) => {
      const rowWidth = rowRef.current?.clientWidth ?? Number.POSITIVE_INFINITY;
      setRightWidth((w) => clampPaneWidth(w - delta, RIGHT_MIN_WIDTH, RIGHT_MAX_WIDTH, leftWidth, rowWidth));
    },
    [leftWidth],
  );

  // Pane sizes only apply from the `@6xl` container width up, so they travel as CSS variables the pane classes read.
  const paneSizes = {
    '--research-left': `${leftWidth}px`,
    '--research-right': `${rightWidth}px`,
    '--research-left-min': `${LEFT_MIN_WIDTH}px`,
    '--research-right-min': `${RIGHT_MIN_WIDTH}px`,
    '--research-center-min': `${CENTER_MIN_WIDTH}px`,
  } as CSSProperties;

  return (
    <div className="@container flex min-h-0 w-full flex-1 flex-col overflow-hidden">
      {/* Below the desktop breakpoint AppLayout floats its sidebar button over the top-left corner; the tabs keep clear of it. */}
      <div className="shrink-0 px-2 pt-2 max-lg:pl-14 @6xl:hidden">
        <Tabs value={activeTab} onValueChange={(tab) => setActiveTab(tab as ResearchTab)}>
          <TabsList className="w-full">
            {PANE_TABS.map(({ tab, icon: Icon }) => (
              <TabsTrigger key={tab} value={tab} aria-controls={paneId(tab)} className="flex-1">
                <Icon className="mr-1.5 h-4 w-4" />
                {t(tab)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div ref={rowRef} className="flex min-h-0 flex-1 overflow-hidden" style={paneSizes}>
        <Pane
          tab="resources"
          label={t('resources')}
          isActive={activeTab === 'resources'}
          className="bg-background @6xl:min-w-(--research-left-min) @6xl:grow-0 @6xl:basis-(--research-left) @6xl:border-r"
        >
          <ResourcePoolPanel />
        </Pane>

        <DragHandle onDrag={handleLeftDrag} />

        <Pane
          tab="chat"
          label={t('chat')}
          isActive={activeTab === 'chat'}
          className="@6xl:min-w-(--research-center-min)"
        >
          <ChatWindow />
        </Pane>

        <DragHandle onDrag={handleRightDrag} />

        <Pane
          tab="output"
          label={t('output')}
          isActive={activeTab === 'output'}
          className="bg-background @6xl:min-w-(--research-right-min) @6xl:grow-0 @6xl:basis-(--research-right) @6xl:border-l"
        >
          <ResearchOutputPanel />
        </Pane>
      </div>
    </div>
  );
}
