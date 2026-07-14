/**
 * MessageSources — 消息引用来源卡片列表
 *
 * [INPUT]
 * store/chat/types/sources::Source, MCPCallRecord (POS: 消息引用来源与 citation 契约)
 * markdown-render-tools/LinkPopover::LinkPopover (POS: 可 hover 预览的链接卡片)
 *
 * [OUTPUT]
 * MessageSources: 渲染消息关联的外部引用来源卡片网格（web/mcp/kb/conversation 四种类型）
 *
 * [POS]
 * 消息引用来源展示组件。以卡片网格形式渲染消息关联的各类外部来源，
 * 支持 web、MCP 技能、知识库、会话历史四种来源类型的差异化图标和 hover 预览。
 */
/* eslint-disable @next/next/no-img-element */
import React, { useCallback, useState } from 'react';
import { File, Puzzle, BookOpen, MessageSquareText } from 'lucide-react';
import { Source, MCPCallRecord } from '@/store/chat/types';
import LinkPopover from '@/components/features/markdown-render-tools/LinkPopover';
import SourceChunkDrawer from './SourceChunkDrawer';
import { useTranslations } from 'next-intl';

type SourceKind = 'web' | 'mcp' | 'kb' | 'conversation' | 'generic';

interface SourceCardData {
  index: number;
  title: string;
  url?: string;
  description?: string;
  kind: SourceKind;
  skillName?: string;
  calls?: MCPCallRecord[];
  section?: string;
}

const CARD_BASE_CLASS =
  'hover:bg-muted hover:shadow-md bg-accent transition-all duration-200 rounded-lg p-3 flex flex-col space-y-2 font-medium';

function getSourceCardData(source: Source, fallbackTitle: string): SourceCardData {
  if (source.type === 'mcp') {
    const skillName = source.skill_name || 'MCP Skill';
    const displayName = skillName.replace(/_mcp_skill$/, '').replace(/_/g, ' ');
    return {
      index: source.index,
      title: displayName,
      kind: 'mcp',
      skillName: source.skill_name,
      calls: source.calls,
    };
  }

  if (source.kb_name) {
    const title = source.filename
      ? `${source.filename}${source.section ? ` § ${source.section}` : ''}`
      : source.kb_name;
    return {
      index: source.index,
      title,
      description: source.snippet || source.summary,
      kind: 'kb',
      section: source.section,
    };
  }

  if (source.type === 'conversation_history') {
    return {
      index: source.index,
      title: source.title || fallbackTitle,
      description: source.snippet || source.summary,
      kind: 'conversation',
    };
  }

  return {
    index: source.index,
    title: source.title || fallbackTitle,
    url: source.url,
    description: source.snippet,
    kind: source.url ? 'web' : 'generic',
  };
}

const SourceIcon = ({ kind, url }: { kind: SourceKind; url?: string }) => {
  switch (kind) {
    case 'mcp':
      return (
        <div className="bg-primary/20 flex items-center justify-center w-6 h-6 rounded-full">
          <Puzzle size={12} className="text-primary" />
        </div>
      );
    case 'kb':
      return (
        <div className="bg-amber-500/20 flex items-center justify-center w-6 h-6 rounded-full">
          <BookOpen size={12} className="text-amber-600 dark:text-amber-400" />
        </div>
      );
    case 'conversation':
      return (
        <div className="bg-blue-500/20 flex items-center justify-center w-6 h-6 rounded-full">
          <MessageSquareText size={12} className="text-blue-600 dark:text-blue-400" />
        </div>
      );
    case 'web':
      return url ? (
        <img
          src={`https://s2.googleusercontent.com/s2/favicons?domain_url=${url}`}
          width={16}
          height={16}
          alt="favicon"
          className="rounded-lg h-4 w-4"
        />
      ) : (
        <div className="bg-muted flex items-center justify-center w-6 h-6 rounded-full">
          <File size={12} className="text-muted-foreground" />
        </div>
      );
    default:
      return (
        <div className="bg-muted flex items-center justify-center w-6 h-6 rounded-full">
          <File size={12} className="text-muted-foreground" />
        </div>
      );
  }
};

const SourceLabel = ({ kind, url, t }: { kind: SourceKind; url?: string; t: ReturnType<typeof useTranslations> }) => {
  const labelMap: Partial<Record<SourceKind, string>> = {
    mcp: t('mcp_skill'),
    kb: t('knowledge_base'),
    conversation: t('conversation_history'),
  };

  if (labelMap[kind]) {
    const colorMap: Partial<Record<SourceKind, string>> = {
      mcp: 'text-primary/70',
      kb: 'text-amber-600/70 dark:text-amber-400/70',
      conversation: 'text-blue-600/70 dark:text-blue-400/70',
    };
    return (
      <p className={`text-xs overflow-hidden whitespace-nowrap text-ellipsis ${colorMap[kind] || 'text-muted-foreground'}`}>
        {labelMap[kind]}
      </p>
    );
  }

  if (kind === 'web' && url) {
    return (
      <p className="text-xs text-muted-foreground overflow-hidden whitespace-nowrap text-ellipsis">
        {url.replace(/.+\/\/|www.|\..+/g, '')}
      </p>
    );
  }

  return null;
};

const SourceCardContent = ({
  data,
  showDescription = false,
  t,
}: {
  data: SourceCardData;
  showDescription?: boolean;
  t: ReturnType<typeof useTranslations>;
}) => (
  <>
    <p
      className={`dark:text-white overflow-hidden whitespace-nowrap text-ellipsis font-medium ${showDescription ? 'text-sm' : 'text-xs'}`}
    >
      {data.title}
    </p>
    <div className="flex flex-row items-center justify-between">
      <div className="flex flex-row items-center space-x-1">
        <SourceIcon kind={data.kind} url={data.url} />
        <SourceLabel kind={data.kind} url={data.url} t={t} />
      </div>
      <div className="flex flex-row items-center space-x-1 text-muted-foreground text-xs">
        <div className="bg-muted-foreground h-[4px] w-[4px] rounded-full" />
        <span>{data.index}</span>
      </div>
    </div>
    {showDescription && data.description && (
      <p className="text-xs text-muted-foreground line-clamp-3 mt-2">{data.description}</p>
    )}
  </>
);

const SourceCard = ({
  data,
  showDescription,
  t,
  onKbClick,
}: {
  data: SourceCardData;
  showDescription: boolean;
  t: ReturnType<typeof useTranslations>;
  onKbClick?: (title: string, section: string | undefined, snippet: string) => void;
}) => {
  const content = <SourceCardContent data={data} showDescription={showDescription} t={t} />;
  const className = showDescription ? CARD_BASE_CLASS : `${CARD_BASE_CLASS} block w-full text-left`;

  if (data.kind === 'web' && data.url) {
    return showDescription ? (
      <a href={data.url} target="_blank" rel="noopener noreferrer" className={className}>
        {content}
      </a>
    ) : (
      <LinkPopover url={data.url} title={data.title} description={data.description} label="">
        <a href={data.url} target="_blank" rel="noopener noreferrer" className={className}>
          {content}
        </a>
      </LinkPopover>
    );
  }

  if (data.kind === 'mcp' && data.calls?.length) {
    const mcpDesc = data.calls.map((c) => `${c.tool_name}: ${c.result_preview || ''}`).join('\n\n');
    return (
      <LinkPopover url="#" title={data.skillName || 'MCP'} description={mcpDesc} label="">
        <div className={`${className} cursor-pointer`}>{content}</div>
      </LinkPopover>
    );
  }

  if (data.kind === 'kb' && data.description && onKbClick) {
    return (
      <button
        className={`${className} cursor-pointer text-left`}
        onClick={() => onKbClick(data.title, data.section, data.description!)}
      >
        {content}
      </button>
    );
  }

  if ((data.kind === 'kb' || data.kind === 'conversation') && data.description) {
    return (
      <LinkPopover url="#" title={data.title} description={data.description} label="">
        <div className={`${className} cursor-pointer`}>{content}</div>
      </LinkPopover>
    );
  }

  return <div className={className}>{content}</div>;
};

const MessageSources = ({ sources }: { sources: Source[] }) => {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [drawerState, setDrawerState] = useState<{
    open: boolean;
    title: string;
    section?: string;
    snippet: string;
  }>({ open: false, title: '', snippet: '' });
  const t = useTranslations('MessageSources');

  const handleKbClick = useCallback((title: string, section: string | undefined, snippet: string) => {
    setDrawerState({ open: true, title, section, snippet });
  }, []);

  return (
    <div className="flex flex-col space-y-2">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {sources.slice(0, 3).map((source, i) => (
          <SourceCard key={i} data={getSourceCardData(source, t('untitled'))} showDescription={false} t={t} onKbClick={handleKbClick} />
        ))}
        {sources.length > 3 && (
          <button
            onClick={() => setIsDialogOpen(true)}
            className="hover:bg-muted hover:shadow-md bg-accent transition-all duration-200 rounded-lg p-3 flex flex-col space-y-2 font-medium"
          >
            <p className="dark:text-white text-xs">{t('view_more', { count: sources.length - 3 })}</p>
          </button>
        )}
      </div>

      {isDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/30" onClick={() => setIsDialogOpen(false)} />
          <div className="relative w-full max-w-md transform rounded-2xl bg-secondary border border-border p-6 text-left align-middle shadow-xl animate-in fade-in-0 zoom-in-95 duration-200">
            <h2 className="text-lg font-medium leading-6 dark:text-white">{t('sources_title')}</h2>
            <div className="grid grid-cols-2 gap-2 overflow-auto max-h-[300px] mt-2 pr-2">
              {sources.map((source, i) => (
                <SourceCard key={i} data={getSourceCardData(source, t('untitled'))} showDescription={true} t={t} onKbClick={handleKbClick} />
              ))}
            </div>
          </div>
        </div>
      )}

      <SourceChunkDrawer
        open={drawerState.open}
        onOpenChange={(open) => setDrawerState((prev) => ({ ...prev, open }))}
        title={drawerState.title}
        section={drawerState.section}
        snippet={drawerState.snippet}
      />
    </div>
  );
};

export default MessageSources;
