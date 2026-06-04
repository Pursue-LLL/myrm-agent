'use client';

/**
 * [INPUT] Pending inline visual approval requests
 * [OUTPUT] Triggers desktop/browser inspector snapshot fetch when screenshot missing
 * [POS] SSE race / refresh fallback for VisualApprovalInlineSection and MobileStatusBoard
 */

import { useEffect, useRef } from 'react';

import { isVisualApprovalToolName } from '@/lib/approval/visualApprovalContext';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

function needsDesktopSnapshot(requests: ToolApprovalRequest[]): boolean {
  return requests.some(
    (request) =>
      isVisualApprovalToolName(request.toolName) &&
      request.toolName.startsWith('desktop_') &&
      !useDesktopInspectorStore.getState().viewData?.screenshotBase64,
  );
}

function needsBrowserSnapshot(requests: ToolApprovalRequest[]): boolean {
  return requests.some(
    (request) =>
      isVisualApprovalToolName(request.toolName) &&
      request.toolName.startsWith('browser_') &&
      !useBrowserInspectorStore.getState().viewData?.screenshotBase64,
  );
}

export function useVisualApprovalSnapshot(requests: ToolApprovalRequest[]): void {
  const fetchedRef = useRef<string>('');

  useEffect(() => {
    if (requests.length === 0) {
      return;
    }

    const key = requests.map((request) => request.requestId).join('|');
    if (fetchedRef.current === key) {
      return;
    }

    const run = async () => {
      const tasks: Promise<void>[] = [];
      if (needsDesktopSnapshot(requests)) {
        tasks.push(useDesktopInspectorStore.getState().fetchSnapshot().then(() => undefined));
      }
      if (needsBrowserSnapshot(requests)) {
        tasks.push(useBrowserInspectorStore.getState().fetchSnapshot().then(() => undefined));
      }
      if (tasks.length > 0) {
        fetchedRef.current = key;
        await Promise.all(tasks);
      }
    };

    void run();
  }, [requests]);
}
