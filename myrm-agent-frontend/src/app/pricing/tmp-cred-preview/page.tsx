'use client';

import { useEffect, useState } from 'react';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

export default function TmpCredPreview() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const original = window.fetch;
    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/approvals/credentials')) {
        return new Response(JSON.stringify({ staged: [{ handle_id: 'cred_ephemeral_demo', key: 'PGPASSWORD' }] }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return original(input, init);
    }) as typeof window.fetch;
    setReady(true);
    return () => {
      window.fetch = original;
    };
  }, []);

  const request: ToolApprovalRequest = {
    requestId: 'req-bash',
    toolName: 'bash_code_execute_tool',
    toolInput: { command: 'psql -h db.internal -U app -c "select count(*) from orders"' },
    reason: 'Run a database query',
    timeoutSeconds: 600,
    expiresAt: Math.floor(Date.now() / 1000) + 600,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-preview',
    actionMode: 'agent',
  };
  return (
    <div className="mx-auto max-w-xl p-4" data-testid="tmp-preview" data-ready={ready}>
      {ready && <SingleApprovalCard request={request} onResolve={async () => {}} isLoading={false} />}
    </div>
  );
}
