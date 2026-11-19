/**
 * [INPUT]
 * ../progress::ProgressItem (POS: 进度条 item 契约)
 * ../sources::Source (POS: citation 来源契约)
 * @/lib/chat/mediaGenerated::MediaGeneratedEntry (POS: 媒体工具登记的生成媒体条目)
 *
 * [OUTPUT]
 * CatchupSnapshotStreamEvent: 断线重连 catch-up 快照 SSE 事件（正文、思考、步骤、来源与已登记的生成媒体）
 *
 * [POS]
 * CatchupSnapshotStreamEvent 类型定义；由 part2.ts 再导出并纳入 AgentStreamEvent 联合。
 */

import type { MediaGeneratedEntry } from '@/lib/chat/mediaGenerated';
import type { ProgressItem } from '../progress';
import type { Source } from '../sources';

export interface CatchupSnapshotStreamEvent {
  type: 'catchup_snapshot';
  messageId: string;
  data: {
    content: string;
    reasoning: string;
    progress_steps: ProgressItem[];
    sources: Source[];
    media_generated: MediaGeneratedEntry[];
  };
}
