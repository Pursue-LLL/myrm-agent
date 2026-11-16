'use client';

/**
 * [INPUT]
 * - @/store/chat/useSubagentStore::SubagentNode, useSubagentStore
 * - @/components/dev/e2eBridge/sendTurnContract::SEND_TURN_REV (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 * - @/components/dev/localDevHost::isLocalDevHost (POS: 开发桥的挂载守卫)
 * - @/components/dev/e2eBridge/sseCapture::createSseCapture (POS: 页面侧 SSE 事件捕获)
 * - @/components/dev/e2eBridge/members/createE2eChatBridge::createE2eChatBridge (POS: 桥成员的汇合处)
 *
 * [OUTPUT]
 * - E2EChatBridge: localhost dev-only component that mounts `window.__MYRM_E2E_CHAT__`, `window.__MYRM_E2E_SUBAGENT__` and the SSE recorder for CDP Chrome E2E
 *
 * [POS]
 * App shell dev bridge。在 MessageInput 水合前挂载，供 CDP/MCP E2E 驱动聊天与 Goal 模式（非终端用户功能）；成员实现按职责分在 e2eBridge/。
 */
import { useLayoutEffect } from 'react';
import { flushSync } from 'react-dom';
import { type SubagentNode, useSubagentStore } from '@/store/chat/useSubagentStore';
import { SEND_TURN_REV } from '@/components/dev/e2eBridge/sendTurnContract';
import { isLocalDevHost } from '@/components/dev/localDevHost';
import { createSseCapture, type SseEventRecorder } from '@/components/dev/e2eBridge/sseCapture';
import { createE2eChatBridge } from '@/components/dev/e2eBridge/members/createE2eChatBridge';

export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) {
      return;
    }

    const sseCapture = createSseCapture();
    (window as Window & { __MYRM_E2E_RECORD_SSE__?: SseEventRecorder }).__MYRM_E2E_RECORD_SSE__ = sseCapture.record;

    (window as unknown as Record<string, unknown>).__MYRM_E2E_SEND_TURN_REV__ = SEND_TURN_REV;

    window.__MYRM_E2E_CHAT__ = createE2eChatBridge(sseCapture.members);

    window.__MYRM_E2E_SUBAGENT__ = {
      hydrate: (rows) => {
        flushSync(() => {
          useSubagentStore.getState().setNodes(rows as unknown as SubagentNode[]);
        });
      },
      nodeCount: () => Object.keys(useSubagentStore.getState().nodes).length,
      refresh: () => undefined,
    };

    return () => {
      delete window.__MYRM_E2E_CHAT__;
      delete window.__MYRM_E2E_SUBAGENT__;
      delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
    };
  }, []);

  return null;
}
