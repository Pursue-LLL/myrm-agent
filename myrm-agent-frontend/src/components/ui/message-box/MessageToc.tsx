import React, { useEffect, useState, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkRehype from 'remark-rehype';
import rehypeRaw from 'rehype-raw';
import { visit } from 'unist-util-visit';
import { ListTree, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface TocItem {
  id: string;
  level: number;
  text: string;
  index: number;
}

interface MessageTocProps {
  content: string;
  isStreaming?: boolean;
  containerRef: React.RefObject<HTMLElement>;
}

export const MessageToc: React.FC<MessageTocProps> = ({ content, isStreaming, containerRef }) => {
  const [toc, setToc] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const t = useTranslations('chat');

  // 1. 提取目录 (使用 remark-parse 保证与 ReactMarkdown 的 AST 解析 100% 一致)
  useEffect(() => {
    if (!content) {
      setToc([]);
      return;
    }

    // 为了避免在流式输出时频繁阻塞主线程，如果是流式状态，我们可以使用 requestIdleCallback 或 setTimeout
    const parseToc = () => {
      try {
        // 使用与 MarkdownContent 完全一致的解析管线 (直到 hast 阶段)
        // 这样可以确保原生 HTML 标签 (如 <h1>) 也能被正确解析和分配索引
        const processor = unified()
          .use(remarkParse)
          .use(remarkGfm)
          .use(remarkRehype, { allowDangerousHtml: true })
          .use(rehypeRaw);

        const hast = processor.runSync(processor.parse(content));
        const newToc: TocItem[] = [];
        let index = 0;

        visit(hast, 'element', (node: any) => {
          if (/^h[1-6]$/.test(node.tagName)) {
            let text = '';
            // 提取 hast 节点中的纯文本
            visit(node, 'text', (textNode: any) => {
              text += textNode.value;
            });

            newToc.push({
              id: `toc-header-${index}`,
              level: parseInt(node.tagName.charAt(1), 10),
              text: text.trim(),
              index,
            });
            index++;
          }
        });

        setToc(newToc);
      } catch (e) {
        console.error('Failed to parse TOC:', e);
      }
    };

    // 流式输出时，降低解析频率以保证打字机效果的流畅性
    if (isStreaming) {
      const timer = setTimeout(parseToc, 500); // 500ms 防抖
      return () => clearTimeout(timer);
    } else {
      parseToc();
    }
  }, [content, isStreaming]);

  // 2. 滚动同步 (Scroll Sync)
  useEffect(() => {
    if (!containerRef.current || toc.length === 0) return;

    // 清理旧的 observer
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    const observerCallback: IntersectionObserverCallback = (entries) => {
      // 找到所有在视口中的标题
      const visibleEntries = entries.filter((entry) => entry.isIntersecting);
      
      if (visibleEntries.length > 0) {
        // 如果有多个标题在视口中，取最上面的一个（即在 DOM 树中靠前的）
        // IntersectionObserver 不保证顺序，所以我们按 y 坐标排序
        visibleEntries.sort((a, b) => a.boundingClientRect.y - b.boundingClientRect.y);
        setActiveId(visibleEntries[0].target.id);
      } else {
        // 如果没有标题在视口中，我们需要判断用户是向上还是向下滚动
        // 但为了简单和性能，如果当前有 activeId，且它滚出了视口上方，我们保持它 active
        // 只有当它滚出视口下方时，我们才可能需要切换到上一个，但这比较复杂。
        // 一个简单的策略是：使用 rootMargin 扩大视口顶部区域，这样标题在离开视口顶部后的一段时间内仍被认为是 intersecting
      }
    };

    observerRef.current = new IntersectionObserver(observerCallback, {
      root: null, // viewport
      rootMargin: '-10% 0px -80% 0px', // 触发线在视口上方 10% 到 20% 的位置
      threshold: 0,
    });

    // 监听所有标题元素
    const headers = containerRef.current.querySelectorAll('h1, h2, h3, h4, h5, h6');
    headers.forEach((header) => observerRef.current?.observe(header));

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [toc, containerRef, isStreaming]); // isStreaming 变化时也重新绑定，因为 DOM 可能更新了

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    const element = document.getElementById(id);
    if (element) {
      // 平滑滚动到目标位置，减去一些 offset 避免被顶部导航栏遮挡
      const y = element.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top: y, behavior: 'smooth' });
      setActiveId(id);
    }
  };

  if (toc.length < 2) {
    return null; // 标题太少不显示目录
  }

  const TocContent = () => (
    <nav className="space-y-1">
      {toc.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          onClick={(e) => handleClick(e, item.id)}
          className={cn(
            'block text-sm py-1 px-2 rounded-md transition-colors duration-200 truncate',
            item.level === 1 && 'font-semibold mt-2',
            item.level === 2 && 'ml-2',
            item.level === 3 && 'ml-4 text-xs',
            item.level >= 4 && 'ml-6 text-xs text-muted-foreground',
            activeId === item.id
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground'
          )}
          title={item.text}
        >
          {item.text}
        </a>
      ))}
    </nav>
  );

  return (
    <>
      {/* 移动端/小屏幕：顶部折叠面板 */}
      <div className="2xl:hidden mb-4">
        <div className="bg-muted/20 border border-border/50 rounded-lg p-3">
          <div 
            className="flex items-center justify-between cursor-pointer group"
            onClick={() => setIsCollapsed(!isCollapsed)}
          >
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">
              <ListTree className="w-4 h-4" />
              <span>{t('tableOfContents') || '目录'}</span>
            </div>
            <ChevronRight 
              className={cn(
                "w-4 h-4 text-muted-foreground transition-transform duration-200",
                !isCollapsed && "rotate-90"
              )} 
            />
          </div>
          
          {!isCollapsed && (
            <div className="mt-3 pt-3 border-t border-border/50 max-h-64 overflow-y-auto">
              <TocContent />
            </div>
          )}
        </div>
      </div>

      {/* 超大屏幕：右侧悬浮面板 */}
      <div className="hidden 2xl:block absolute left-full top-0 bottom-0 ml-8 w-64 z-10 pointer-events-none">
        <div className="sticky top-24 max-h-[80vh] overflow-y-auto bg-background/50 backdrop-blur-sm border border-border/50 rounded-xl p-4 shadow-sm pointer-events-auto">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3">
            <ListTree className="w-4 h-4" />
            <span>{t('tableOfContents') || '目录'}</span>
          </div>
          <TocContent />
        </div>
      </div>
    </>
  );
};
