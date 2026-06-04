'use client';

/**
 * [INPUT] Pending inline visual approval requests
 * [OUTPUT] Snapshot fetch lifecycle + retry for visual approval cards
 * [POS] SSE race / refresh fallback for VisualApprovalInlineSection and MobileStatusBoard
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { isVisualApprovalToolName } from '@/lib/approval/visualApprovalContext';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

export type VisualApprovalSnapshotStatus = 'idle' | 'loading' | 'ready' | 'failed';

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

function hasSnapshotForRequests(requests: ToolApprovalRequest[]): boolean {
  const needsDesktop = requests.some(
    (request) => isVisualApprovalToolName(request.toolName) && request.toolName.startsWith('desktop_'),
  );
  const needsBrowser = requests.some(
    (request) => isVisualApprovalToolName(request.toolName) && request.toolName.startsWith('browser_'),
  );

  if (needsDesktop && !useDesktopInspectorStore.getState().viewData?.screenshotBase64) {
    return false;
  }
  if (needsBrowser && !useBrowserInspectorStore.getState().viewData?.screenshotBase64) {
    return false;
  }
  return true;
}

export function useVisualApprovalSnapshot(requests: ToolApprovalRequest[]): {
  status: VisualApprovalSnapshotStatus;
  snapshotFetchFailed: boolean;
  retrySnapshot: () => void;
} {
  const [status, setStatus] = useState<VisualApprovalSnapshotStatus>('idle');
  const fetchedKeyRef = useRef('');

  const runFetch = useCallback(
    async (force = false) => {
      if (requests.length === 0) {
        setStatus('idle');
        return;
      }

      const key = requests.map((request) => request.requestId).join('|');
      if (!force && fetchedKeyRef.current === key && hasSnapshotForRequests(requests)) {
        setStatus('ready');
        return;
      }

      const tasks: Promise<boolean>[] = [];
      if (needsDesktopSnapshot(requests)) {
        tasks.push(useDesktopInspectorStore.getState().fetchSnapshot());
      }
      if (needsBrowserSnapshot(requests)) {
        tasks.push(useBrowserInspectorStore.getState().fetchSnapshot());
      }

      if (tasks.length === 0) {
        setStatus(hasSnapshotForRequests(requests) ? 'ready' : 'failed');
        fetchedKeyRef.current = key;
        return;
      }

      setStatus('loading');
      const results = await Promise.all(tasks);
      fetchedKeyRef.current = key;

      if (results.every(Boolean) && hasSnapshotForRequests(requests)) {
        setStatus('ready');
        return;
      }

      setStatus('failed');
    },
    [requests],
  );

  useEffect(() => {
    void runFetch();
  }, [runFetch]);

  const retrySnapshot = useCallback(() => {
    fetchedKeyRef.current = '';
    void runFetch(true);
  }, [runFetch]);

  return {
    status,
    snapshotFetchFailed: status === 'failed',
    retrySnapshot,
  };
}
