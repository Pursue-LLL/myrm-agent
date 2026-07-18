/**
 * [INPUT]
 * ../progress::ProgressItem (POS: 进度条 item 契约)
 * ../sources::Source (POS: citation 来源契约)
 *
 * [OUTPUT]
 * CatchupSnapshotStreamEvent: 断线重连 catch-up 快照 SSE 事件
 *
 * [POS]
 * CatchupSnapshotStreamEvent 类型定义；由 part2.ts 再导出并纳入 AgentStreamEvent 联合。
 */

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
  };
}
