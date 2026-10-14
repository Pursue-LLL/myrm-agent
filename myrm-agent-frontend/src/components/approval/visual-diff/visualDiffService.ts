/**
 * [INPUT]
 * visualDiffTypes.ts
 * [OUTPUT]
 * VisualDiffService providing bidirectional approval API transport and offline fallback.
 * [POS]
 * src/components/approval/visual-diff/visualDiffService.ts
 */

import {
  ApprovalAck,
  StructuredApprovalDecision,
  StructuredApprovalRequest,
} from './visualDiffTypes';

export class VisualDiffService {
  private readonly baseUrl: string;

  constructor(baseUrl: string = '/api/v1/approvals/bidirectional') {
    this.baseUrl = baseUrl;
  }

  async createFileDiffRequest(params: {
    sessionId: string;
    filePath: string;
    newContent: string;
    oldContent?: string | null;
    summary?: string;
  }): Promise<StructuredApprovalRequest> {
    try {
      const response = await fetch(`${this.baseUrl}/file-diff-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: params.sessionId,
          file_path: params.filePath,
          new_content: params.newContent,
          old_content: params.oldContent,
          summary: params.summary,
        }),
      });

      if (response.ok) {
        return (await response.json()) as StructuredApprovalRequest;
      }
    } catch {
      // Fallback below
    }

    // Offline simulation fallback
    const mockDiff = `--- a/${params.filePath}\n+++ b/${params.filePath}\n@@ -1,1 +1,2 @@\n ${params.oldContent || ''}\n+${params.newContent}`;
    return {
      approval_id: `offline-appr-${Date.now()}`,
      session_id: params.sessionId,
      sequence_id: 1,
      kind: 'file_write',
      summary: params.summary || `File change for ${params.filePath}`,
      file_diff: {
        file_path: params.filePath,
        old_content: params.oldContent,
        new_content: params.newContent,
        unified_diff: mockDiff,
        added_lines: 1,
        removed_lines: 0,
        is_new_file: !params.oldContent,
        is_deletion: false,
      },
      command_risk: null,
      created_at: Date.now() / 1000,
      expires_at: Date.now() / 1000 + 300,
      allowed_decisions: ['allow', 'reject', 'remember_session'],
    };
  }

  async createCommandRequest(params: {
    sessionId: string;
    command: string;
    cwd: string;
    summary?: string;
  }): Promise<StructuredApprovalRequest> {
    try {
      const response = await fetch(`${this.baseUrl}/command-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: params.sessionId,
          command: params.command,
          cwd: params.cwd,
          summary: params.summary,
        }),
      });

      if (response.ok) {
        return (await response.json()) as StructuredApprovalRequest;
      }
    } catch {
      // Fallback below
    }

    const isHighRisk = params.command.includes('rm -rf') || params.command.includes('sudo');
    return {
      approval_id: `offline-cmd-${Date.now()}`,
      session_id: params.sessionId,
      sequence_id: 1,
      kind: 'command_exec',
      summary: params.summary || `Command execution: ${params.command}`,
      file_diff: null,
      command_risk: {
        command: params.command,
        cwd: params.cwd,
        risk_severity: isHighRisk ? 'critical' : 'low',
        risk_reasons: isHighRisk ? ['Destructive recursive file deletion'] : ['Standard command'],
        blast_radius_paths: [params.cwd],
      },
      created_at: Date.now() / 1000,
      expires_at: Date.now() / 1000 + 300,
      allowed_decisions: ['allow', 'reject', 'remember_session'],
    };
  }

  async submitDecision(decision: StructuredApprovalDecision): Promise<ApprovalAck> {
    try {
      const response = await fetch(`${this.baseUrl}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(decision),
      });

      if (response.ok) {
        return (await response.json()) as ApprovalAck;
      }
    } catch {
      // Offline fallback
    }

    return {
      approval_id: decision.approval_id,
      sequence_id: 1,
      acknowledged: true,
      status: `resolved_${decision.decision}`,
    };
  }

  async fetchPendingApprovals(sessionId?: string): Promise<StructuredApprovalRequest[]> {
    const url = sessionId
      ? `${this.baseUrl}/pending?session_id=${encodeURIComponent(sessionId)}`
      : `${this.baseUrl}/pending`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        return (await response.json()) as StructuredApprovalRequest[];
      }
    } catch {
      // Fallback
    }

    return [];
  }
}

export const visualDiffService = new VisualDiffService();
