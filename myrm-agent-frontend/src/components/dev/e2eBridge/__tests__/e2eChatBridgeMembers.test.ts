/**
 * The E2E bridge provides the member set the Python dev tooling calls by name.
 *
 * Real scenario: the bridge members live in separate groups that are spread into one object, so a member dropped from
 * a group, or defined by two groups (the later spread silently wins), breaks CDP E2E runs without any type error.
 */
import { describe, expect, it } from 'vitest';

import { createE2eChatBridge } from '@/components/dev/e2eBridge/members/createE2eChatBridge';
import { createBrowserTakeoverMembers } from '@/components/dev/e2eBridge/members/browserTakeover';
import { createComposerMembers } from '@/components/dev/e2eBridge/members/composer';
import { createGoalMembers } from '@/components/dev/e2eBridge/members/goal';
import { createInspectorMembers } from '@/components/dev/e2eBridge/members/inspectors';
import { createProviderMembers } from '@/components/dev/e2eBridge/members/providers';
import { createSendMembers } from '@/components/dev/e2eBridge/members/send';
import { createSessionMembers } from '@/components/dev/e2eBridge/members/session';
import { createStreamControlMembers } from '@/components/dev/e2eBridge/members/streamControl';
import { createSseCapture } from '@/components/dev/e2eBridge/sseCapture';

const BRIDGE_MEMBERS = [
  '__e2eFallback',
  'abortActiveStream',
  'allocateStreamMessageId',
  'attachToChat',
  'clearSearchServicesForE2e',
  'clearSseSnapshot',
  'clearStreamRequestMessageId',
  'closeRewindDialog',
  'completeBrowserTakeoverWithResume',
  'debugProviderState',
  'debugSearchState',
  'debugSecurityState',
  'dismissBrowserTakeover',
  'dispatchBackgroundJobFinishAndRefresh',
  'dispatchSystemNotification',
  'ensureChatSession',
  'ensureComputerUseReady',
  'ensureProviders',
  'ephSubagentsStatus',
  'forkFirstContextBranchBookmark',
  'getActionMode',
  'getActiveGoalSnapshot',
  'getBrowserInspectorSnapshot',
  'getBrowserSource',
  'getBrowserTakeoverSnapshot',
  'getBrowserToolProgress',
  'getChatShellState',
  'getCurrentBuiltinTools',
  'getDesktopApprovalSnapshot',
  'getDesktopInspectorSnapshot',
  'getDesktopToolProgress',
  'getFastSearchProgressSnapshot',
  'getFirstDesktopDref',
  'getGoalDraftState',
  'getGoalMode',
  'getInputMessage',
  'getLastAssistantMessageId',
  'getRewindTarget',
  'getSearchDepth',
  'handleSubmit',
  'hideApprovalDrawer',
  'isApprovalDrawerOpen',
  'isProvidersInitialized',
  'isSendReady',
  'isWorkflowMode',
  'kickoffChatMessage',
  'loadActiveGoalFromApi',
  'openRewindDialog',
  'peekOutboundUserMessage',
  'pinBasicModelForE2e',
  'pinLiteModelForE2e',
  'pokeChatRouteRender',
  'prefetchSlashSkillCatalog',
  'prepareAutomationSend',
  'recoverHitlStream',
  'recoverPendingBrowserTakeover',
  'releaseActiveStreamForApiResume',
  'releaseAgentModelPinForE2e',
  'resetChat',
  'retryStreamWithSameMessageId',
  'runGoalDraftFromComposer',
  'sendChatMessage',
  'sendTurnRev',
  'sendWorkflowTemplateRun',
  'setActionMode',
  'setBrowserSource',
  'setCurrentBuiltinTools',
  'setGoalBudgetTokens',
  'setGoalConvergenceWindow',
  'setGoalMode',
  'setInputMessage',
  'setLoading',
  'setSearchDepth',
  'setSseCaptureMessageId',
  'setToolsSnapshotForE2e',
  'setWorkflowMode',
  'simulateBrowserToolStart',
  'simulateBrowserViewUpdate',
  'simulateDesktopControlApprovalRequest',
  'simulateDesktopViewUpdate',
  'skipActiveClarificationForE2e',
  'ssePayloadSnapshot',
  'sseSnapshot',
  'submitAndObserveTurn',
  'submitSteerNudge',
  'syncDesktopControlApproval',
  'syncSearchServicesFromE2eApi',
  'toolApprovalSnapshot',
  'triggerBrowserTakeover',
  'turnSnapshot',
];

const FLAG_MEMBERS = ['__e2eFallback'];

function memberGroups(): Array<Record<string, unknown>> {
  return [
    createProviderMembers(),
    createSessionMembers(),
    createSendMembers(),
    createGoalMembers(),
    createComposerMembers(),
    createStreamControlMembers(),
    createBrowserTakeoverMembers(),
    createInspectorMembers(),
    createSseCapture().members,
  ];
}

describe('E2E chat bridge members', () => {
  it('provides exactly the members the dev tooling calls', () => {
    const bridge = createE2eChatBridge(createSseCapture().members);

    expect(Object.keys(bridge).sort()).toEqual([...BRIDGE_MEMBERS].sort());
  });

  it('defines every member in exactly one group', () => {
    const keys = memberGroups().flatMap((group) => Object.keys(group));

    expect(keys).toHaveLength(BRIDGE_MEMBERS.length);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('exposes every member as a function except the fallback flag', () => {
    const bridge = createE2eChatBridge(createSseCapture().members) as unknown as Record<string, unknown>;

    for (const name of BRIDGE_MEMBERS) {
      expect(typeof bridge[name], name).toBe(FLAG_MEMBERS.includes(name) ? 'boolean' : 'function');
    }
  });
});
