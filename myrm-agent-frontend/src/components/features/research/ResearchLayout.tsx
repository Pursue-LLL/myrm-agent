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
 * Research 三栏布局入口。PC 模式可拖拽分割线三栏并列，移动端降级为 Tab 切换。
 */

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { BookOpen, MessageSquare, FileText } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives/tabs';
import { useIsMobile } from '@/hooks/useMediaQuery';
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

interface DragHandleProps {
  onDrag: (deltaX: number) => void;
}

function DragHandle({ onDrag }: DragHandleProps) {
  const isDragging = useRef(false);
  const lastX = useRef(0);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      isDragging.current = true;
      lastX.current = e.clientX;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return;
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
      className="w-1.5 shrink-0 cursor-col-resize flex items-center justify-center group hover:bg-primary/10 transition-colors"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div className="w-0.5 h-8 rounded-full bg-border group-hover:bg-primary/40 transition-colors" />
    </div>
  );
}

export default function ResearchLayout() {
  const t = useTranslations('research');
  const isMobile = useIsMobile();
  const { activeTab, setActiveTab } = useResearchStore();
  useResearchSync();

  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT_WIDTH);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT_WIDTH);

  const handleLeftDrag = useCallback((delta: number) => {
    setLeftWidth((w) => Math.min(LEFT_MAX_WIDTH, Math.max(LEFT_MIN_WIDTH, w + delta)));
  }, []);

  const handleRightDrag = useCallback((delta: number) => {
    setRightWidth((w) => Math.min(RIGHT_MAX_WIDTH, Math.max(RIGHT_MIN_WIDTH, w - delta)));
  }, []);

  if (isMobile) {
    return (
      <div className="flex flex-col h-full">
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as ResearchTab)}
          className="flex flex-col h-full"
        >
          <TabsList className="shrink-0 mx-2 mt-2">
            <TabsTrigger value="resources" className="flex-1">
              <BookOpen className="w-4 h-4 mr-1.5" />
              {t('resources')}
            </TabsTrigger>
            <TabsTrigger value="chat" className="flex-1">
              <MessageSquare className="w-4 h-4 mr-1.5" />
              {t('chat')}
            </TabsTrigger>
            <TabsTrigger value="output" className="flex-1">
              <FileText className="w-4 h-4 mr-1.5" />
              {t('output')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="resources" className="flex-1 min-h-0">
            <ResourcePoolPanel />
          </TabsContent>
          <TabsContent value="chat" className="flex-1 min-h-0">
            <ChatWindow />
          </TabsContent>
          <TabsContent value="output" className="flex-1 min-h-0">
            <ResearchOutputPanel />
          </TabsContent>
        </Tabs>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Left: Resource Pool */}
      <div
        className="shrink-0 border-r bg-background overflow-hidden"
        style={{ width: leftWidth }}
      >
        <ResourcePoolPanel />
      </div>

      <DragHandle onDrag={handleLeftDrag} />

      {/* Center: Chat */}
      <div className="flex-1 min-w-0 overflow-hidden">
        <ChatWindow />
      </div>

      <DragHandle onDrag={handleRightDrag} />

      {/* Right: Output */}
      <div
        className="shrink-0 border-l bg-background overflow-hidden"
        style={{ width: rightWidth }}
      >
        <ResearchOutputPanel />
      </div>
    </div>
  );
}
