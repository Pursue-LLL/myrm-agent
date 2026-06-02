/**
 * 对话跳转导航栏
 *
 * [INPUT]
 * - messages: Message[] (POS: 聊天消息列表)
 * - onJump: (messageIndex: number) => void (POS: 跳转回调)
 * - loading: boolean (POS: 是否正在生成)
 *
 * [OUTPUT]
 * - ConversationJumpBar: PC 端右侧悬浮 dot 导航
 * - MobileJumpBarSheet: 移动端 Sheet 消息列表导航
 *
 * [POS]
 * 长对话快速定位导航。PC 端在右侧显示垂直 dot 条，
 * 悬停显示波纹宽度动画和消息预览气泡，点击跳转。
 * 移动端通过 Sheet/Drawer 展示消息摘要列表。
 */

'use client';

import { useMemo, useRef, useState, useCallback, memo } from 'react';
import type { Message } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';
import { stripDatetimeTag, stripMarkdown } from '@/lib/utils/messageUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { useTranslations } from 'next-intl';

/** user 消息 >= 此数量时才显示导航 */
const MIN_USER_MESSAGES = 3;

/** 预览文本最大长度 */
const PREVIEW_TEXT_LENGTH = 80;

interface JumpItem {
  index: number;
  text: string;
}

interface ConversationJumpBarProps {
  messages: Message[];
  onJump: (messageIndex: number) => void;
  loading?: boolean;
  hasGoalPanel?: boolean;
}

/** 从消息列表中提取 user 消息的索引和预览文本 */
function extractUserItems(messages: Message[]): JumpItem[] {
  const items: JumpItem[] = [];
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === 'user' && msg.content) {
      const cleanText = stripMarkdown(stripDatetimeTag(msg.content));
      if (cleanText) {
        items.push({
          index: i,
          text: cleanText.slice(0, PREVIEW_TEXT_LENGTH),
        });
      }
    }
  }
  return items;
}

// ─── PC 端 Dot 导航 ───────────────────────────────────

/** dot 波纹宽度：距离 hover 中心越近越宽 */
function dotWidth(idx: number, hoverIdx: number): number {
  if (hoverIdx < 0) return 12;
  const d = Math.abs(idx - hoverIdx);
  if (d === 0) return 32;
  if (d === 1) return 20;
  if (d === 2) return 14;
  return 12;
}

/** dot 错开延迟：距离 hover 中心越远延迟越大 */
function dotDelay(idx: number, hoverIdx: number): string {
  if (hoverIdx < 0) return '0ms';
  return `${Math.abs(idx - hoverIdx) * 20}ms`;
}

const ConversationJumpBar = memo<ConversationJumpBarProps>(({ messages, onJump, loading, hasGoalPanel }) => {
  const t = useTranslations('chat.jumpBar');
  const [hoveredIdx, setHoveredIdx] = useState(-1);
  const [showPreview, setShowPreview] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const previewTopRef = useRef(0);

  const items = useMemo(() => extractUserItems(messages), [messages]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const el = barRef.current;
      if (!el) return;
      const dots = el.querySelectorAll<HTMLElement>('[data-jump-dot]');
      const barRect = el.getBoundingClientRect();
      let closest = -1;
      let closestDist = Infinity;

      dots.forEach((dot, i) => {
        const r = dot.getBoundingClientRect();
        const midY = r.top + r.height / 2;
        const dist = Math.abs(e.clientY - midY);
        if (dist < closestDist) {
          closestDist = dist;
          closest = i;
          previewTopRef.current = midY - barRect.top;
        }
      });

      if (closest >= 0 && closest < items.length) {
        setHoveredIdx(closest);
        setShowPreview(true);
      }
    },
    [items.length],
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredIdx(-1);
    setShowPreview(false);
  }, []);

  const handleDotClick = useCallback(
    (itemIndex: number) => {
      onJump(items[itemIndex].index);
    },
    [items, onJump],
  );

  if (items.length < MIN_USER_MESSAGES) return null;

  const hoverText = hoveredIdx >= 0 ? items[hoveredIdx]?.text : null;

  return (
    <div
      ref={barRef}
      className={cn(
        'fixed top-1/2 -translate-y-1/2 z-30 flex flex-col items-center py-3 px-1.5',
        'hidden md:flex',
        'transition-opacity duration-300',
        loading ? 'opacity-40' : 'opacity-100',
        hasGoalPanel ? 'right-[340px]' : 'right-3',
      )}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      aria-label={t('ariaLabel')}
    >
      {/* Dot 列表 */}
      <div className="flex flex-col gap-1.5 items-center max-h-[calc(100vh-6rem)] overflow-y-auto scrollbar-hide">
        {items.map((item, idx) => (
          <button
            key={item.index}
            data-jump-dot
            className="group flex items-center justify-center cursor-pointer p-0 border-0 bg-transparent"
            style={{ height: 12 }}
            onClick={() => handleDotClick(idx)}
            aria-label={`${t('jumpTo')} ${idx + 1}`}
          >
            <div
              className={cn(
                'h-[5px] rounded-full transition-all ease-out',
                hoveredIdx >= 0 && Math.abs(idx - hoveredIdx) <= 2 ? 'bg-primary' : 'bg-muted-foreground/30',
              )}
              style={{
                width: dotWidth(idx, hoveredIdx),
                transitionDelay: dotDelay(idx, hoveredIdx),
                transitionDuration: '150ms',
              }}
            />
          </button>
        ))}
      </div>

      {/* 预览气泡 */}
      {showPreview && hoverText && (
        <div
          className="absolute right-full mr-2.5 max-w-[240px] px-3 py-1.5 rounded-lg
              bg-popover text-popover-foreground text-xs leading-relaxed
              shadow-md border border-border
              pointer-events-none whitespace-nowrap overflow-hidden text-ellipsis"
          style={{ top: previewTopRef.current, transform: 'translateY(-50%)' }}
        >
          {hoverText}
        </div>
      )}
    </div>
  );
});

ConversationJumpBar.displayName = 'ConversationJumpBar';

// ─── 移动端 Sheet 导航 ─────────────────────────────────

interface MobileJumpBarSheetProps {
  messages: Message[];
  onJump: (messageIndex: number) => void;
  trigger: React.ReactNode;
}

const MobileJumpBarSheet = memo<MobileJumpBarSheetProps>(({ messages, onJump, trigger }) => {
  const t = useTranslations('chat.jumpBar');
  const [open, setOpen] = useState(false);
  const items = useMemo(() => extractUserItems(messages), [messages]);

  const handleSelect = useCallback(
    (messageIndex: number) => {
      onJump(messageIndex);
      setOpen(false);
    },
    [onJump],
  );

  if (items.length < MIN_USER_MESSAGES) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="bottom" className="max-h-[60vh]">
        <SheetHeader>
          <SheetTitle>{t('title')}</SheetTitle>
        </SheetHeader>
        <div className="overflow-y-auto mt-3 -mx-6 px-6 space-y-1">
          {items.map((item, idx) => (
            <button
              key={item.index}
              className="w-full text-left px-3 py-2.5 rounded-md
                  text-sm text-foreground/80 hover:bg-accent
                  transition-colors cursor-pointer truncate
                  border-0 bg-transparent"
              onClick={() => handleSelect(item.index)}
            >
              <span className="text-muted-foreground mr-2 text-xs font-mono">{idx + 1}.</span>
              {item.text}
            </button>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
});

MobileJumpBarSheet.displayName = 'MobileJumpBarSheet';

export { ConversationJumpBar, MobileJumpBarSheet };
export type { ConversationJumpBarProps, MobileJumpBarSheetProps };
