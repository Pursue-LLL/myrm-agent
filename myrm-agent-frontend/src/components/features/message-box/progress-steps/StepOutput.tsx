/**
 * [INPUT]
 * - ./renderers::* (POS: 步骤多态渲染器与终端)
 * - ./utils::* (POS: items 类型守卫与委派工具行判断)
 * - @/lib/utils/urlUtils::isUrl (POS: 链接判断)
 *
 * [OUTPUT]
 * - StepItemsView: 按 items 的形态选择渲染器，输出步骤的结构化内容。
 * - StepTerminal: 步骤的实时终端输出与被 evict 的完整输出入口。
 *
 * [POS]
 * 进度步骤的产出展示：计划节点与委派工具行（标题已是它本身）不再渲染一遍 items；
 * 点击文本中的链接交给 utils::handleLinkClick 在新标签页打开。
 */

import type { ProgressItem } from '@/store/chat/types';
import { isUrl } from '@/lib/utils/urlUtils';
import {
  CodeRenderer,
  FilePathRenderer,
  LiveTerminal,
  QueryItemsRenderer,
  SearchToolCard,
  SkillSelectRenderer,
  SourcesRenderer,
  TextItemsRenderer,
  TextRenderer,
  URLItemsRenderer,
} from './renderers';
import {
  handleLinkClick,
  isCodeItems,
  isDelegationToolLine,
  isFilePathItems,
  isQueryItems,
  isSearchToolItems,
  isSkillSelectItems,
  isSourceItems,
  isTextItems,
  isTextString,
  isUrlItems,
} from './utils';

interface StepItemsViewProps {
  step: ProgressItem;
  messageId: string;
  /** Position of the step in the message's step list. */
  index: number;
  isCurrent: boolean;
}

const openLinkText = (text: string): void => handleLinkClick(text, isUrl(text));

export function StepItemsView({ step, messageId, index, isCurrent }: StepItemsViewProps) {
  const { items } = step;
  if (!items || step.is_plan || isDelegationToolLine(step)) {
    return null;
  }

  return (
    <div>
      {isSkillSelectItems(items) && <SkillSelectRenderer items={items} messageId={messageId} stepIndex={index} />}
      {isFilePathItems(items) && <FilePathRenderer items={items} messageId={messageId} stepIndex={index} />}
      {isSearchToolItems(items) && (
        <SearchToolCard items={items} toolName={step.tool_name} messageId={messageId} stepIndex={index} />
      )}
      {isCodeItems(items) && <CodeRenderer items={items} messageId={messageId} stepIndex={index} />}
      {isTextItems(items) && (
        <TextItemsRenderer items={items} messageId={messageId} stepIndex={index} handleLinkClick={openLinkText} />
      )}
      {isQueryItems(items) && <QueryItemsRenderer items={items} messageId={messageId} stepIndex={index} />}
      {isTextString(items) && <TextRenderer text={items} />}
      {isSourceItems(items) ? (
        <SourcesRenderer items={items} messageId={messageId} stepIndex={index} isCurrentStep={isCurrent} />
      ) : (
        isUrlItems(items) && (
          <URLItemsRenderer
            items={items}
            messageId={messageId}
            stepIndex={index}
            isCurrentStep={isCurrent}
            handleLinkClick={openLinkText}
          />
        )
      )}
    </div>
  );
}

export function StepTerminal({ step }: { step: ProgressItem }) {
  return (
    <LiveTerminal
      stdout={step.stdout}
      evictedFileRef={step.evicted_file_ref}
      evictedStoredChars={step.evicted_stored_chars}
      evictedTotalLines={step.evicted_total_lines}
      evictedStorageTruncated={step.evicted_storage_truncated}
      evictedStderrFileRef={step.evicted_stderr_file_ref}
      evictedStderrStoredChars={step.evicted_stderr_stored_chars}
      evictedStderrTotalLines={step.evicted_stderr_total_lines}
      evictedStderrStorageTruncated={step.evicted_stderr_storage_truncated}
    />
  );
}
