/* eslint-disable @next/next/no-img-element */
import React, { useState } from 'react';
import { File, Puzzle } from 'lucide-react';
import { Source } from '@/store/chat/types';
import LinkPopover from '@/components/features/markdown-render-tools/LinkPopover';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';
import { useTranslations } from 'next-intl';

interface MCPCall {
  tool_name: string;
  result_preview: string;
}

interface SourceCardData {
  index: number;
  title: string;
  url?: string;
  description?: string;
  isMcp: boolean;
  skillName?: string;
  calls?: MCPCall[];
}

const MessageSources = ({ sources }: { sources: Source[] }) => {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const t = useTranslations('MessageSources');

  const closeModal = () => {
    setIsDialogOpen(false);
  };

  const openModal = () => {
    setIsDialogOpen(true);
  };

  // 将 Source 转换为卡片数据
  const getSourceCardData = (source: Source): SourceCardData => {
    const isMcp = source.type === 'mcp';

    if (isMcp) {
      // 优化显示：只显示技能名，调用详情在 hover 时展示
      const skillName = source.skill_name || 'MCP Skill';
      // 提取更友好的技能名：去掉 _mcp_skill 后缀
      const displayName = skillName.replace(/_mcp_skill$/, '').replace(/_/g, ' ');
      return {
        index: source.index,
        title: displayName,
        isMcp: true,
        skillName: source.skill_name,
        calls: source.calls,
      };
    }

    return {
      index: source.index,
      title: source.title || t('untitled'),
      url: source.url,
      description: source.snippet,
      isMcp: false,
    };
  };

  // 渲染源内容
  const renderSourceContent = (source: Source, index: number) => {
    const cardData = getSourceCardData(source);

    const content = (
      <>
        <p className="dark:text-white text-xs overflow-hidden whitespace-nowrap text-ellipsis font-medium">
          {cardData.title}
        </p>
        <div className="flex flex-row items-center justify-between">
          <div className="flex flex-row items-center space-x-1">
            {cardData.isMcp ? (
              <div className="bg-primary/20 flex items-center justify-center w-6 h-6 rounded-full">
                <Puzzle size={12} className="text-primary" />
              </div>
            ) : cardData.url ? (
              <img
                src={`https://s2.googleusercontent.com/s2/favicons?domain_url=${cardData.url}`}
                width={16}
                height={16}
                alt="favicon"
                className="rounded-lg h-4 w-4"
              />
            ) : (
              <div className="bg-muted flex items-center justify-center w-6 h-6 rounded-full">
                <File size={12} className="text-muted-foreground" />
              </div>
            )}
            {cardData.isMcp ? (
              <p className="text-xs text-primary/70 overflow-hidden whitespace-nowrap text-ellipsis">
                {t('mcp_skill')}
              </p>
            ) : cardData.url ? (
              <p className="text-xs text-muted-foreground overflow-hidden whitespace-nowrap text-ellipsis">
                {cardData.url.replace(/.+\/\/|www.|\..+/g, '')}
              </p>
            ) : null}
          </div>
          <div className="flex flex-row items-center space-x-1 text-muted-foreground text-xs">
            <div className="bg-muted-foreground h-[4px] w-[4px] rounded-full" />
            <span>{cardData.index}</span>
          </div>
        </div>
      </>
    );

    const className =
      'hover:bg-muted hover:shadow-md bg-accent transition-all duration-200 rounded-lg p-3 flex flex-col space-y-2 font-medium block w-full text-left';

    // 网页类型使用 LinkPopover 包装
    if (!cardData.isMcp && cardData.url) {
      return (
        <LinkPopover
          key={index}
          url={cardData.url}
          title={cardData.title}
          description={cardData.description}
          label=""
          className="w-full"
        >
          <a href={cardData.url} target="_blank" rel="noopener noreferrer" className={className}>
            {content}
          </a>
        </LinkPopover>
      );
    }

    // MCP 技能：使用 HoverCard 展示调用详情
    if (cardData.isMcp && cardData.calls && cardData.calls.length > 0) {
      return (
        <HoverCard key={index}>
          <HoverCardTrigger asChild>
            <div className={`${className} cursor-pointer`}>{content}</div>
          </HoverCardTrigger>
          <HoverCardContent className="w-80 max-h-80 overflow-auto">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Puzzle size={16} className="text-primary" />
                <span className="font-medium text-sm">{cardData.skillName}</span>
              </div>
              <p className="text-xs text-muted-foreground">{t('mcp_calls_count', { count: cardData.calls.length })}</p>
              <div className="space-y-2 mt-2">
                {cardData.calls.map((call, callIndex) => (
                  <div key={callIndex} className="bg-muted rounded-full p-2">
                    <p className="text-xs font-medium text-primary">{call.tool_name}</p>
                    {call.result_preview && (
                      <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap break-all line-clamp-4">
                        {call.result_preview}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </HoverCardContent>
        </HoverCard>
      );
    }

    // 无 URL 的源（如知识库）
    return (
      <div key={index} className={className}>
        {content}
      </div>
    );
  };

  // 渲染对话框中的源项目内容
  const renderDialogSourceContent = (source: Source, index: number) => {
    const cardData = getSourceCardData(source);

    const content = (
      <>
        <p className="dark:text-white text-sm overflow-hidden whitespace-nowrap text-ellipsis font-medium">
          {cardData.title}
        </p>
        <div className="flex flex-row items-center justify-between">
          <div className="flex flex-row items-center space-x-1">
            {cardData.isMcp ? (
              <div className="bg-primary/20 flex items-center justify-center w-6 h-6 rounded-full">
                <Puzzle size={12} className="text-primary" />
              </div>
            ) : cardData.url ? (
              <img
                src={`https://s2.googleusercontent.com/s2/favicons?domain_url=${cardData.url}`}
                width={16}
                height={16}
                alt="favicon"
                className="rounded-lg h-4 w-4"
              />
            ) : (
              <div className="bg-muted flex items-center justify-center w-6 h-6 rounded-full">
                <File size={12} className="text-muted-foreground" />
              </div>
            )}
            {cardData.isMcp ? (
              <p className="text-xs text-primary/70 overflow-hidden whitespace-nowrap text-ellipsis">
                {t('mcp_skill')}
              </p>
            ) : cardData.url ? (
              <p className="text-xs text-muted-foreground overflow-hidden whitespace-nowrap text-ellipsis">
                {cardData.url.replace(/.+\/\/|www.|\..+/g, '')}
              </p>
            ) : null}
          </div>
          <div className="flex flex-row items-center space-x-1 text-muted-foreground text-xs">
            <div className="bg-muted-foreground h-[4px] w-[4px] rounded-full" />
            <span>{cardData.index}</span>
          </div>
        </div>
        {cardData.description && (
          <p className="text-xs text-muted-foreground line-clamp-3 mt-2">{cardData.description}</p>
        )}
      </>
    );

    const className =
      'hover:bg-muted hover:shadow-md bg-accent transition-all duration-200 rounded-lg p-3 flex flex-col space-y-2';

    if (!cardData.isMcp && cardData.url) {
      return (
        <a key={index} href={cardData.url} target="_blank" rel="noopener noreferrer" className={className}>
          {content}
        </a>
      );
    }

    // MCP 技能：使用 HoverCard 展示调用详情
    if (cardData.isMcp && cardData.calls && cardData.calls.length > 0) {
      return (
        <HoverCard key={index}>
          <HoverCardTrigger asChild>
            <div className={`${className} cursor-pointer`}>{content}</div>
          </HoverCardTrigger>
          <HoverCardContent className="w-80 max-h-80 overflow-auto">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Puzzle size={16} className="text-primary" />
                <span className="font-medium text-sm">{cardData.skillName}</span>
              </div>
              <p className="text-xs text-muted-foreground">{t('mcp_calls_count', { count: cardData.calls.length })}</p>
              <div className="space-y-2 mt-2">
                {cardData.calls.map((call, callIndex) => (
                  <div key={callIndex} className="bg-muted rounded-full p-2">
                    <p className="text-xs font-medium text-primary">{call.tool_name}</p>
                    {call.result_preview && (
                      <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap break-all line-clamp-4">
                        {call.result_preview}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </HoverCardContent>
        </HoverCard>
      );
    }

    return (
      <div key={index} className={className}>
        {content}
      </div>
    );
  };

  return (
    <div className="flex flex-col space-y-2">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {sources.slice(0, 3).map((source, i) => renderSourceContent(source, i))}
        {sources.length > 3 && (
          <button
            onClick={openModal}
            className="hover:bg-muted hover:shadow-md bg-accent transition-all duration-200 rounded-lg p-3 flex flex-col space-y-2 font-medium"
          >
            <p className="dark:text-white text-xs">{t('view_more', { count: sources.length - 3 })}</p>
          </button>
        )}
      </div>

      {/* 模态对话框 */}
      {isDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/30" onClick={closeModal} />
          <div className="relative w-full max-w-md transform rounded-2xl bg-secondary border border-border p-6 text-left align-middle shadow-xl animate-in fade-in-0 zoom-in-95 duration-200">
            <h2 className="text-lg font-medium leading-6 dark:text-white">{t('sources_title')}</h2>
            <div className="grid grid-cols-2 gap-2 overflow-auto max-h-[300px] mt-2 pr-2">
              {sources.map((source, i) => renderDialogSourceContent(source, i))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MessageSources;
