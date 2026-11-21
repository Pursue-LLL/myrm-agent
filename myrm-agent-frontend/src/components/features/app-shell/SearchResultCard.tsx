'use client';

/**
 * [INPUT]
 * - @/services/chatHistorySearch::SearchResult (POS: 历史消息搜索命中项契约)
 * - @/lib/utils/classnameUtils::cn (POS: className 合并)
 * - next-intl::useTranslations (POS: 卡片文案)
 *
 * [OUTPUT]
 * - SearchResultCard: Cmd+K 的一条搜索结果：点击打开会话并定位到命中消息，旁边的按钮把该会话引用进输入框；命中消息的发言方按当前语言标为「你 / 助手」。
 *
 * [POS]
 * search-dialog 的结果项子组件。卡片本身不可交互：标题是原生按钮，其 ::after 铺满整张卡片（点卡片任意处等于点它）；
 * 引用按钮是它的同级兄弟、叠在铺满层之上。Enter / Space 因此天然各归各的按钮，不需要任何按键拦截。
 */

import { useId } from 'react';
import { Calendar, MessageSquare } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { SearchResult } from '@/services/chatHistorySearch';

interface SearchResultCardProps {
  item: SearchResult;
  /** Opens the chat at the matched message. */
  onOpen: () => void;
  /** Cites the chat into the composer. */
  onCite: () => void;
}

const CITE_BUTTON_CLASS =
  'relative z-10 px-2 py-0.5 text-[11px] font-medium rounded-full border border-border/60 bg-background/80 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/40';

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '';
  }
}

export function SearchResultCard({ item, onOpen, onCite }: SearchResultCardProps) {
  const t = useTranslations();
  const snippetId = useId();
  const isUserMessage = item.role === 'user';

  return (
    <div className="relative w-full p-3 rounded-lg hover:bg-muted/50 focus-within:bg-muted/50 transition-colors flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        {/* Hits of one chat share its title, so the snippet is what tells them apart to a screen reader. */}
        <button
          type="button"
          aria-describedby={snippetId}
          onClick={onOpen}
          className="flex items-center gap-2 min-w-0 text-left text-sm font-medium text-foreground after:absolute after:inset-0"
        >
          <MessageSquare className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <span className="truncate">{item.chat_title || t('chat.newChat')}</span>
        </button>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            data-cite-to-composer
            onClick={onCite}
            className={cn(CITE_BUTTON_CLASS, 'hidden sm:inline-flex')}
          >
            {t('search.citeToComposer')}
          </button>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Calendar className="w-3 h-3" />
            <span>{formatDate(item.sent_at)}</span>
          </div>
        </div>
      </div>
      <div id={snippetId} className="text-sm text-muted-foreground line-clamp-2 pl-5">
        <span
          className={cn(
            'inline-block px-1.5 py-0.5 rounded text-[10px] font-medium mr-2 uppercase',
            isUserMessage ? 'bg-primary/10 text-primary' : 'bg-secondary text-secondary-foreground',
          )}
        >
          {isUserMessage ? t('search.roleUser') : t('search.roleAssistant')}
        </span>
        <span
          dangerouslySetInnerHTML={{
            __html: item.snippet,
          }}
        />
      </div>
      <button
        type="button"
        data-cite-to-composer
        onClick={onCite}
        className={cn(CITE_BUTTON_CLASS, 'sm:hidden self-start ml-5')}
      >
        {t('search.citeToComposer')}
      </button>
    </div>
  );
}
