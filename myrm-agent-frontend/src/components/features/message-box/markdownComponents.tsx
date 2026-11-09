/**
 * markdownComponents - MarkdownContent 的元素映射表
 *
 * [POS]
 * 把 Markdown 元素与自定义标签（vault、think 系列、citation）映射到具体渲染组件。
 *
 * [关键职责]
 * - code：mermaid / diff / 内联 HTML 预览 / 高亮代码块 / 交付物引用 / 行内代码
 * - a：外链样式；非流式时为可嵌入链接渲染嵌入卡片、为裸链接渲染 OgCard
 * - citation：web / mcp / 知识库 / 会话历史四种来源的引用角标（知识库来源经 openKbDrawer 打开侧栏）
 */
import type React from 'react';
import type { Components } from 'react-markdown';
import { cn } from '@/lib/utils/classnameUtils';
import { INLINE_CODE_CHIP } from '@/lib/constants/codeblock-theme';
import LinkPopover from '@/components/features/markdown-render-tools/LinkPopover';
import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import InlineHtmlWidget from '@/components/features/markdown-render-tools/InlineHtmlWidget';
import MermaidChart from '@/components/features/markdown-render-tools/MermaidChart';
import ThinkTagProcessor from '../markdown-render-tools/ThinkTagProcessor';
import MarkdownImage from '../markdown-render-tools/MarkdownImage';
import { getChildrenAsText } from '@/lib/utils/reactUtils';
import VaultArtifactCard from '../artifacts/VaultArtifactCard';
import InlineDiffViewer from '../markdown-render-tools/InlineDiffViewer';
import ResponsiveTable from '../markdown-render-tools/ResponsiveTable';
import type { Artifact, Source, WikiSourceLevel } from '@/store/chat/types';
import { buildWikiAssetUrl } from '@/services/wikiService';
import { resolveWikiSectionLabel } from '@/services/wiki/sectionLabels';
import { detectEmbed, UrlEmbed } from '@/components/features/embeds';
import { OgCard } from '@/components/features/embeds/OgCard';
import DeliverableReferenceLink from './DeliverableReferenceLink';
import { parseDeliverableReference } from '@/lib/deliverable-link/parseDeliverableReference';

const INLINE_RENDER_LANGUAGES = new Set(['html', 'svg']);

function normalizeWikiLevel(level: Source['level']): WikiSourceLevel | undefined {
  if (level === 'L0' || level === 'L1' || level === 'L2') {
    return level;
  }
  return undefined;
}

type MarkdownCodeProps = React.HTMLAttributes<HTMLElement> & {
  node?: {
    position?: {
      start?: { line?: number };
      end?: { line?: number };
    };
  };
  className?: string;
  children?: React.ReactNode;
};

type CitationProps = {
  [key: string]: string | undefined;
};

export type OpenKbDrawer = (
  title: string,
  section: string | undefined,
  snippet: string,
  level?: WikiSourceLevel,
  snapshotStatus?: Source['snapshot_status'],
  thumbnailUrl?: string | null,
  resourceUri?: string,
  supersededFromUri?: string,
  claimStatus?: Source['claim_status'],
  claimConfidence?: Source['claim_confidence'],
  claimText?: Source['claim_text'],
) => void;

type MarkdownComponentsOptions = {
  sources: Source[];
  isStreaming: boolean;
  openKbDrawer: OpenKbDrawer;
  tSources: (key: string) => string;
  chatId?: string;
  messageArtifacts?: Artifact[];
  workspaceDir?: string;
};

export function createMarkdownComponents({
  sources,
  isStreaming,
  openKbDrawer,
  tSources,
  chatId,
  messageArtifacts,
  workspaceDir,
}: MarkdownComponentsOptions): Components {
  return {
    vault: ({ id }: { id?: string }) => {
      if (!id) {
        return null;
      }
      return <VaultArtifactCard id={id} chatId={chatId} />;
    },
    think: ThinkTagProcessor,
    thinking: ThinkTagProcessor,
    thought: ThinkTagProcessor,
    antthinking: ThinkTagProcessor,
    reasoning: ThinkTagProcessor,
    code: ({ node, className, children, ...props }: MarkdownCodeProps) => {
      const match = /language-(\w+)/.exec(className || '');
      const language = match && match[1] ? match[1] : '';
      const value = getChildrenAsText(children);

      if (language === 'mermaid' && value.trim()) {
        return <MermaidChart chart={value} />;
      }

      if (language === 'diff' && value.trim()) {
        return <InlineDiffViewer diff={value} />;
      }

      if (!isStreaming && INLINE_RENDER_LANGUAGES.has(language.toLowerCase()) && value.trim()) {
        return <InlineHtmlWidget language={language} value={value} />;
      }

      if (language) {
        return <CodeBlock language={language} value={value} isStreaming={isStreaming} />;
      }

      // 内联代码块 — deliverable workspace / artifact references
      const isInlineCode = node?.position?.start?.line === node?.position?.end?.line;
      if (isInlineCode && !isStreaming) {
        const deliverableRef = parseDeliverableReference(value);
        if (deliverableRef) {
          return (
            <DeliverableReferenceLink
              reference={deliverableRef}
              label={value}
              chatId={chatId}
              workspaceDir={workspaceDir}
              messageArtifacts={messageArtifacts}
            />
          );
        }
      }
      if (isInlineCode) {
        return (
          <code className={cn(INLINE_CODE_CHIP, 'font-normal')} {...props}>
            {value}
          </code>
        );
      }

      // 普通文本
      return <span>{value}</span>;
    },
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
      const isExternal = href && /^https?:\/\//.test(href);
      if (isExternal) {
        const embedDescriptor = !isStreaming ? detectEmbed(href) : null;
        if (embedDescriptor) {
          return (
            <span className="block">
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors"
              >
                {children}
              </a>
              <UrlEmbed descriptor={embedDescriptor} />
            </span>
          );
        }

        const childText = typeof children === 'string' ? children : '';
        const isBareLinkInParagraph = childText === href || childText === href.replace(/^https?:\/\//, '');
        if (!isStreaming && isBareLinkInParagraph) {
          return (
            <span className="block">
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors"
              >
                {children}
              </a>
              <OgCard url={href} />
            </span>
          );
        }

        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors"
          >
            {children}
          </a>
        );
      }
      return <a href={href}>{children}</a>;
    },
    img: ({ src, alt }: { src?: string; alt?: string }) => <MarkdownImage src={src} alt={alt} />,
    table: ({ children }: { children?: React.ReactNode }) => (
      <ResponsiveTable isStreaming={isStreaming}>{children}</ResponsiveTable>
    ),
    citation: (props: CitationProps) => {
      const url = props['data-url'];
      const num = props['data-num'];
      const sourceIndex = Number.parseInt(props['data-source-index'] || '', 10);

      if (isNaN(sourceIndex) || !sources || sourceIndex >= sources.length) {
        return <>[{num}]</>;
      }

      const source = sources[sourceIndex];

      if (source?.type === 'mcp') {
        const mcpTitle = source.skill_name || 'MCP Skill';
        const mcpCalls = Array.isArray(source.calls) ? source.calls : [];
        const mcpDescription =
          mcpCalls.length > 0
            ? mcpCalls
                .map(
                  (call: { tool_name: string; result_preview?: string }) =>
                    `${call.tool_name}: ${call.result_preview || ''}`,
                )
                .join('\n\n')
            : '';
        return <LinkPopover url="#" title={mcpTitle} description={mcpDescription} label={num} />;
      }

      if (source?.kb_name) {
        const sectionLabel = resolveWikiSectionLabel(source.section, tSources);
        const kbTitle = source.filename
          ? `${source.filename}${sectionLabel ? ` § ${sectionLabel}` : ''}`
          : source.kb_name;
        const kbSnippet = source.snippet || source.summary || '';
        const assetThumbnailUrl =
          source.hit_kind === 'asset' && source.asset_filename
            ? buildWikiAssetUrl(source.asset_filename, source.agent_id)
            : null;
        if (kbSnippet) {
          return (
            <button
              type="button"
              className="bg-secondary px-1 rounded ml-1 no-underline text-xs text-black/70 dark:text-white/70 relative hover:bg-amber-500/30 hover:text-amber-800 dark:hover:text-amber-300 transition-colors duration-200 cursor-pointer inline-flex items-center"
              onClick={() =>
                openKbDrawer(
                  kbTitle,
                  sectionLabel,
                  kbSnippet,
                  normalizeWikiLevel(source.level),
                  source.snapshot_status,
                  assetThumbnailUrl,
                  source.resource_uri,
                  source.superseded_from_uri,
                  source.claim_status,
                  source.claim_confidence,
                  source.claim_text,
                )
              }
            >
              {num}
            </button>
          );
        }
        return <LinkPopover url="#" title={kbTitle} description="" label={num} />;
      }

      if (source?.type === 'conversation_history') {
        return (
          <LinkPopover
            url="#"
            title={source.title || 'Conversation'}
            description={source.snippet || source.summary || ''}
            label={num}
          />
        );
      }

      // 默认渲染网页引用 (web_search, web_fetch)
      const title = source?.title;
      const description = source?.summary || source?.snippet;
      const linkUrl = url && url !== '' ? url : '#';

      return (
        <LinkPopover
          url={linkUrl}
          title={title}
          description={description}
          label={num}
          siteName={source?.site_name}
          authority={source?.authority_description}
          date={source?.date}
        />
      );
    },
  } as Components;
}
