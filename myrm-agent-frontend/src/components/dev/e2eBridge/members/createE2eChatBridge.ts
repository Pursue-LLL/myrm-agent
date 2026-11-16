/**
 * [INPUT]
 * - @/components/dev/e2eBridge/members/providers::createProviderMembers (POS: 桥成员（provider 与模型）)
 * - @/components/dev/e2eBridge/members/session::createSessionMembers (POS: 桥成员（聊天会话）)
 * - @/components/dev/e2eBridge/members/send::createSendMembers (POS: 桥成员（发送）)
 * - @/components/dev/e2eBridge/members/goal::createGoalMembers (POS: 桥成员（目标与回退）)
 * - @/components/dev/e2eBridge/members/composer::createComposerMembers (POS: 桥成员（输入区设置）)
 * - @/components/dev/e2eBridge/members/streamControl::createStreamControlMembers (POS: 桥成员（流控制）)
 * - @/components/dev/e2eBridge/members/browserTakeover::createBrowserTakeoverMembers (POS: 桥成员（浏览器接管）)
 * - @/components/dev/e2eBridge/members/inspectors::createInspectorMembers (POS: 桥成员（检查器）)
 *
 * [OUTPUT]
 * - createE2eChatBridge(sseMembers): the complete `window.__MYRM_E2E_CHAT__` object
 *
 * [POS]
 * 桥成员的汇合处：把各成员分组与 SSE 捕获的成员组装成 `window.__MYRM_E2E_CHAT__`。
 */
import { createProviderMembers } from '@/components/dev/e2eBridge/members/providers';
import { createSessionMembers } from '@/components/dev/e2eBridge/members/session';
import { createSendMembers } from '@/components/dev/e2eBridge/members/send';
import { createGoalMembers } from '@/components/dev/e2eBridge/members/goal';
import { createComposerMembers } from '@/components/dev/e2eBridge/members/composer';
import { createStreamControlMembers } from '@/components/dev/e2eBridge/members/streamControl';
import { createBrowserTakeoverMembers } from '@/components/dev/e2eBridge/members/browserTakeover';
import { createInspectorMembers } from '@/components/dev/e2eBridge/members/inspectors';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

/** Assembles `window.__MYRM_E2E_CHAT__` from the member groups and the SSE capture's members. */
export function createE2eChatBridge(sseMembers: E2eBridgeMembers): NonNullable<Window['__MYRM_E2E_CHAT__']> {
  return {
    ...createProviderMembers(),
    ...createSessionMembers(),
    ...createSendMembers(),
    ...createGoalMembers(),
    ...createComposerMembers(),
    ...createStreamControlMembers(),
    ...createBrowserTakeoverMembers(),
    ...createInspectorMembers(),
    ...sseMembers,
  } as NonNullable<Window['__MYRM_E2E_CHAT__']>;
}
