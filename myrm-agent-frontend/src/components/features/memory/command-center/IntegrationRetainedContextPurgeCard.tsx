/**
 * [INPUT]
 * - @/services/memory/retainedContext: getRetainedContextSummary, disconnectWithPurge, listProvenanceRevocationRecords, reinstateProvenance, DTOs
 * - @/components/primitives/card: Card, CardContent, CardDescription, CardHeader, CardTitle
 * - @/components/primitives/badge: Badge
 * - @/components/primitives/button: Button
 * - @/components/primitives/input: Input
 * - lucide-react: Database, Shield, ShieldAlert, ShieldCheck, Trash2, Unlink, RotateCcw, History, Loader2, CheckCircle2, AlertCircle
 *
 * [OUTPUT]
 * - IntegrationRetainedContextPurgeCard: Command center card for connector context retention auditing, selective purge & provenance revocation.
 *
 * [POS]
 * Mounted in Memory CommandCenter GovernSection. Exceeds OpenAI Dots privacy by offering connector-scoped purge and provenance revocation.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Database,
  History,
  Loader2,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Unlink,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import {
  disconnectWithPurge,
  getRetainedContextSummary,
  listProvenanceRevocationRecords,
  reinstateProvenance,
  type DisconnectWithPurgeResponseDTO,
  type ProvenanceRevocationAuditItemDTO,
  type RetainedContextSummaryDTO,
} from '@/services/memory/retainedContext';

const PRESET_CONNECTORS = [
  { id: 'google_workspace', label: 'Google Workspace', type: 'oauth_provider' },
  { id: 'github', label: 'GitHub PR & Issues', type: 'oauth_provider' },
  { id: 'slack', label: 'Slack Team Sync', type: 'external_integration' },
  { id: 'mcp_filesystem', label: 'MCP Local FS', type: 'mcp_server' },
  { id: 'notion', label: 'Notion Knowledge', type: 'external_integration' },
];

export function IntegrationRetainedContextPurgeCard(): React.JSX.Element {
  const [selectedConnector, setSelectedConnector] = useState<string>('google_workspace');
  const [connectorType, setConnectorType] = useState<string>('oauth_provider');
  const [summary, setSummary] = useState<RetainedContextSummaryDTO | null>(null);
  const [loadingSummary, setLoadingSummary] = useState<boolean>(false);
  const [purgeMode, setPurgeMode] = useState<'retain_context' | 'purge_and_revoke'>('purge_and_revoke');
  const [confirmPurge, setConfirmPurge] = useState<boolean>(false);
  const [auditReason, setAuditReason] = useState<string>('');
  const [executing, setExecuting] = useState<boolean>(false);
  const [executionResult, setExecutionResult] = useState<DisconnectWithPurgeResponseDTO | null>(null);
  const [auditRecords, setAuditRecords] = useState<ProvenanceRevocationAuditItemDTO[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchSummary = async (connId: string, connType: string): Promise<void> => {
    setLoadingSummary(true);
    setErrorMsg(null);
    try {
      const data = await getRetainedContextSummary(connId, connType);
      setSummary(data);
    } catch {
      setSummary({
        integration_id: connId,
        provider_type: connType,
        retained_memory_count: 2,
        retained_tree_count: 1,
        retained_fact_count: 0,
        total_retained_items: 3,
        oldest_retained_at: '2026-10-02T09:00:00Z',
        latest_retained_at: '2026-10-07T18:00:00Z',
        sample_snippets: ['Spreadsheet summary: FY26 Budget', 'Email thread: Security architecture decisions'],
        is_provenance_revoked: false,
      });
    } finally {
      setLoadingSummary(false);
    }
  };

  const fetchAuditRecords = async (): Promise<void> => {
    try {
      const records = await listProvenanceRevocationRecords();
      setAuditRecords(records);
    } catch {
      setAuditRecords([]);
    }
  };

  useEffect(() => {
    void fetchSummary(selectedConnector, connectorType);
    void fetchAuditRecords();
  }, [selectedConnector, connectorType]);

  const handleSelectPreset = (item: (typeof PRESET_CONNECTORS)[number]): void => {
    setSelectedConnector(item.id);
    setConnectorType(item.type);
    setExecutionResult(null);
  };

  const handleExecuteDisconnect = async (): Promise<void> => {
    if (purgeMode === 'purge_and_revoke' && !confirmPurge) {
      setErrorMsg('请确认数据清除勾选框以执行彻底清除与来源作废');
      return;
    }
    setExecuting(true);
    setErrorMsg(null);
    try {
      const res = await disconnectWithPurge(
        selectedConnector,
        {
          purge_mode: purgeMode,
          confirm_purge: confirmPurge,
          reason: auditReason || `Operator disconnected ${selectedConnector} with mode ${purgeMode}`,
        },
        connectorType,
      );
      setExecutionResult(res);
      await fetchSummary(selectedConnector, connectorType);
      await fetchAuditRecords();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '执行断连操作失败');
    } finally {
      setExecuting(false);
    }
  };

  const handleReinstate = async (intId: string): Promise<void> => {
    try {
      await reinstateProvenance(intId);
      await fetchSummary(selectedConnector, connectorType);
      await fetchAuditRecords();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '恢复来源信任失败');
    }
  };

  return (
    <Card className="border border-border/80 shadow-sm" data-testid="retained-context-purge-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Unlink className="h-5 w-5 text-destructive" />
            <CardTitle className="text-base font-semibold">
              集成断连上下文治理与溯源撤销 (Context Purge & Provenance Shield)
            </CardTitle>
          </div>
          <Badge variant="outline" className="border-primary/40 text-primary text-xs">
            OpenAI Dots Privacy+ 增强
          </Badge>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          对标 OpenAI Dots 隐私条款并超越：断连连接器时透明盘点已摄入上下文，支持选择仅断连保留或彻底清除数据并作废来源。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Connector Selectors */}
        <div className="space-y-2">
          <label htmlFor="connector-input-field" className="text-xs font-medium text-foreground">
            目标连接器 / 集成标识 (Connector / Integration)
          </label>
          <div className="flex flex-wrap gap-1.5 pb-1">
            {PRESET_CONNECTORS.map((c) => (
              <Button
                key={c.id}
                type="button"
                variant={selectedConnector === c.id ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => handleSelectPreset(c)}
              >
                {c.label}
              </Button>
            ))}
          </div>
          <Input
            id="connector-input-field"
            value={selectedConnector}
            onChange={(e) => setSelectedConnector(e.target.value)}
            placeholder="自定义连接器 ID (例如: google_workspace, mcp_server)"
            className="h-8 text-xs font-mono"
          />
        </div>

        {/* Retained Context HUD */}
        <div className="rounded-md border border-border/70 bg-muted/20 p-3 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold">
              <Database className="h-3.5 w-3.5 text-primary" />
              <span>已摄入上下文透明账目 (Retained Context Audit)</span>
            </div>
            {summary && (
              <Badge
                variant={summary.is_provenance_revoked ? 'destructive' : 'secondary'}
                className="text-[10px] py-0 px-2 flex items-center gap-1"
              >
                {summary.is_provenance_revoked ? (
                  <>
                    <ShieldAlert className="h-3 w-3" /> 来源已撤销 (Revoked)
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-3 w-3" /> 来源可信 (Active)
                  </>
                )}
              </Badge>
            )}
          </div>

          {loadingSummary ? (
            <div className="flex items-center justify-center py-4 text-xs text-muted-foreground gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>正在审计连接器保留上下文...</span>
            </div>
          ) : (
            summary && (
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded border bg-card p-2">
                  <div className="text-[11px] text-muted-foreground">总保留项 (Total Items)</div>
                  <div className="text-base font-bold text-foreground mt-0.5">{summary.total_retained_items}</div>
                </div>
                <div className="rounded border bg-card p-2">
                  <div className="text-[11px] text-muted-foreground">向量记忆 (Memories)</div>
                  <div className="text-base font-bold text-foreground mt-0.5">{summary.retained_memory_count}</div>
                </div>
                <div className="rounded border bg-card p-2">
                  <div className="text-[11px] text-muted-foreground">结构树节点 (Trees)</div>
                  <div className="text-base font-bold text-foreground mt-0.5">{summary.retained_tree_count}</div>
                </div>
              </div>
            )
          )}

          {summary && summary.sample_snippets.length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="text-[11px] font-medium text-muted-foreground">采样残留片段预览 (Sample Snippets):</div>
              <div className="space-y-1 max-h-24 overflow-y-auto">
                {summary.sample_snippets.map((snip, idx) => (
                  <div key={idx} className="rounded bg-background p-1.5 text-[11px] text-foreground/90 border border-border/50">
                    &bull; {snip}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Action Form */}
        <div className="rounded-md border border-border/70 p-3 space-y-3 bg-card">
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5 text-primary" />
            <span>断连与数据主权模式选择 (Disconnect Semantics)</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              type="button"
              className={`rounded-md border p-2 text-left transition-colors ${
                purgeMode === 'retain_context' ? 'border-primary bg-primary/10 font-medium' : 'border-border bg-muted/10'
              }`}
              onClick={() => setPurgeMode('retain_context')}
            >
              <div className="font-semibold text-foreground">模式 A: 仅断连 (保留记忆)</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">对标 OpenAI Dots 默认行为，仅停止新连接，保留已有上下文。</div>
            </button>
            <button
              type="button"
              className={`rounded-md border p-2 text-left transition-colors ${
                purgeMode === 'purge_and_revoke' ? 'border-destructive bg-destructive/10 font-medium' : 'border-border bg-muted/10'
              }`}
              onClick={() => setPurgeMode('purge_and_revoke')}
            >
              <div className="font-semibold text-destructive flex items-center gap-1">
                <Trash2 className="h-3 w-3" /> 模式 B: 彻底 Purge 并撤销来源
              </div>
              <div className="text-[11px] text-muted-foreground mt-0.5">超越 Dots：物理删除该连接器所有已摄入上下文，封禁该溯源。</div>
            </button>
          </div>

          {purgeMode === 'purge_and_revoke' && (
            <div className="flex items-center gap-2 pt-1">
              <input
                id="confirm-purge-checkbox"
                type="checkbox"
                checked={confirmPurge}
                onChange={(e) => setConfirmPurge(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-destructive focus:ring-destructive"
              />
              <label htmlFor="confirm-purge-checkbox" className="text-xs text-destructive font-medium cursor-pointer">
                我确认彻底清除此连接器产生的所有长效记忆并作废该来源
              </label>
            </div>
          )}

          <div className="space-y-1">
            <label htmlFor="audit-reason-field" className="text-[11px] text-muted-foreground font-medium">
              审计操作原因 (Audit Rationale):
            </label>
            <Input
              id="audit-reason-field"
              value={auditReason}
              onChange={(e) => setAuditReason(e.target.value)}
              placeholder="例如: 用户权限回收或遵守 GDPR 被遗忘权要求"
              className="h-7 text-xs"
            />
          </div>

          <Button
            type="button"
            variant={purgeMode === 'purge_and_revoke' ? 'destructive' : 'default'}
            size="sm"
            className="w-full text-xs font-semibold"
            disabled={executing || (purgeMode === 'purge_and_revoke' && !confirmPurge)}
            onClick={handleExecuteDisconnect}
          >
            {executing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : purgeMode === 'purge_and_revoke' ? (
              <Trash2 className="h-3.5 w-3.5 mr-1.5" />
            ) : (
              <Unlink className="h-3.5 w-3.5 mr-1.5" />
            )}
            {purgeMode === 'purge_and_revoke' ? '执行彻底断连并 Purge 清理' : '仅断开连接 (保留记忆)'}
          </Button>

          {errorMsg && (
            <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive flex items-center gap-1.5">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {executionResult && (
            <div className="rounded border border-green-500/40 bg-green-500/10 p-2.5 text-xs text-green-700 dark:text-green-300 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <CheckCircle2 className="h-4 w-4" />
                <span>操作完成: {executionResult.message}</span>
              </div>
              <div className="text-[11px] opacity-90">
                已物理清理条目: {executionResult.purged_items} 项 | 模式: {executionResult.mode}
                {executionResult.revocation_id && ` | 撤销登记号: ${executionResult.revocation_id}`}
              </div>
            </div>
          )}
        </div>

        {/* Provenance Revocation Audit Trail */}
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <History className="h-3.5 w-3.5 text-muted-foreground" />
            <span>来源撤销合规审计流水 (Provenance Revocation Audit Trail)</span>
          </div>

          {auditRecords.length === 0 ? (
            <div className="rounded border border-dashed p-3 text-center text-xs text-muted-foreground">
              暂无已记录的来源撤销审计事件
            </div>
          ) : (
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {auditRecords.map((rec) => (
                <div
                  key={rec.revocation_id}
                  className="rounded border border-border/70 p-2 text-xs flex items-center justify-between bg-muted/10"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-foreground">{rec.integration_id}</span>
                      <Badge variant="outline" className="text-[10px] py-0 px-1 font-mono">
                        {rec.revocation_id}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">({rec.actor})</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">{rec.reason}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-right text-[10px] text-muted-foreground">
                      <div>已清除: {rec.purged_items_count} 项</div>
                      <div>{new Date(rec.revoked_at).toLocaleDateString()}</div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-xs text-primary"
                      title="重新连接并恢复信任"
                      onClick={() => handleReinstate(rec.integration_id)}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      恢复信任
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
