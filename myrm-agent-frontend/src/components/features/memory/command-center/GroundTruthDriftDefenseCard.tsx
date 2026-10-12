/**
 * [INPUT]
 * - @/services/memory/driftDefense: checkMemoryDrift, checkBatchMemoryDrift, DriftCheckResponseDTO, BatchDriftCheckResponseDTO
 * - @/components/primitives/card: Card, CardContent, CardDescription, CardHeader, CardTitle
 * - @/components/primitives/input: Input
 * - @/components/primitives/button: Button
 * - @/components/primitives/textarea: Textarea
 * - @/components/features/memory/command-center/DriftReferenceAuditView: DriftReferenceAuditView
 *
 * [OUTPUT]
 * - GroundTruthDriftDefenseCard: Primary card for ground truth code drift defense & stale memory prevention.
 *
 * [POS]
 * Management card in Memory CommandCenter UnderstandSection for ground truth physical verification.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  FileSearch,
  Layers,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';

import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { DriftReferenceAuditView } from './DriftReferenceAuditView';
import {
  checkBatchMemoryDrift,
  checkMemoryDrift,
  type BatchDriftCheckResponseDTO,
  type DriftCheckResponseDTO,
} from '@/services/memory/driftDefense';

export function GroundTruthDriftDefenseCard() {
  const [memoryId, setMemoryId] = useState('mem-drift-probe-01');
  const [workspaceRoot, setWorkspaceRoot] = useState('');
  const [recordedPath, setRecordedPath] = useState('src/services/auth.py');
  const [recordedSymbol, setRecordedSymbol] = useState('AuthService');
  const [content, setContent] = useState(
    'Use src/services/auth.py AuthService to authenticate user tokens and permissions.'
  );

  const [loading, setLoading] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [singleResult, setSingleResult] = useState<DriftCheckResponseDTO | null>(null);
  const [batchResult, setBatchResult] = useState<BatchDriftCheckResponseDTO | null>(null);

  const handleSingleCheck = async () => {
    if (!content.trim() || !memoryId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await checkMemoryDrift({
        memory_id: memoryId.trim(),
        content: content.trim(),
        workspace_root: workspaceRoot.trim() || null,
        recorded_path: recordedPath.trim() || null,
        recorded_symbol: recordedSymbol.trim() || null,
      });
      setSingleResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '物理代码漂移检测失败');
    } finally {
      setLoading(false);
    }
  };

  const handleBatchCheck = async () => {
    setBatchLoading(true);
    setError(null);
    try {
      const res = await checkBatchMemoryDrift({
        workspace_root: workspaceRoot.trim() || null,
        items: [
          {
            memory_id: 'probe-valid-01',
            content: 'Reference src/services/auth.py AuthService',
            recorded_path: 'src/services/auth.py',
            recorded_symbol: 'AuthService',
          },
          {
            memory_id: 'probe-missing-file-02',
            content: 'Legacy database settings in config/deprecated_db.json',
            recorded_path: 'config/deprecated_db.json',
          },
          {
            memory_id: 'probe-missing-symbol-03',
            content: 'Old token cipher in src/services/auth.py LegacyCipher',
            recorded_path: 'src/services/auth.py',
            recorded_symbol: 'LegacyCipher',
          },
        ],
      });
      setBatchResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '批量漂移检测失败');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleLoadDriftExample = () => {
    setMemoryId('mem-stale-example');
    setRecordedPath('src/legacy/obsolete_module.py');
    setRecordedSymbol('OldValidator');
    setContent('Legacy validation flow implemented in src/legacy/obsolete_module.py OldValidator.');
  };

  return (
    <Card className="border-border/70 shadow-sm">
      <CardHeader className="space-y-1 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              Ground Truth 真实性漂移防御与过时记忆熔断
            </CardTitle>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadDriftExample}
            className="text-xs h-7"
          >
            <RefreshCw className="mr-1.5 h-3 w-3" />
            载入过时样本
          </Button>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          毫秒级扫描工作区物理文件与 AST 符号，在记忆检索与 Prompt 注入前熔断已删除/重构的虚假代码记忆，注入过时警告并扣减置信度。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="space-y-1">
            <label htmlFor="drift-memory-id" className="font-medium text-foreground">
              记忆标识 (Memory ID)
            </label>
            <Input
              id="drift-memory-id"
              value={memoryId}
              onChange={(e) => setMemoryId(e.target.value)}
              placeholder="e.g. mem-001"
              className="h-8 text-xs font-mono"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="drift-workspace-root" className="font-medium text-foreground">
              工作区根目录 (Workspace Root, 可选)
            </label>
            <Input
              id="drift-workspace-root"
              value={workspaceRoot}
              onChange={(e) => setWorkspaceRoot(e.target.value)}
              placeholder="留空使用当前服务工作区"
              className="h-8 text-xs font-mono"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="drift-recorded-path" className="font-medium text-foreground">
              绑定物理文件路径 (Recorded Path)
            </label>
            <Input
              id="drift-recorded-path"
              value={recordedPath}
              onChange={(e) => setRecordedPath(e.target.value)}
              placeholder="e.g. src/services/auth.py"
              className="h-8 text-xs font-mono"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="drift-recorded-symbol" className="font-medium text-foreground">
              绑定 AST 类/函数符号 (Recorded Symbol)
            </label>
            <Input
              id="drift-recorded-symbol"
              value={recordedSymbol}
              onChange={(e) => setRecordedSymbol(e.target.value)}
              placeholder="e.g. AuthService"
              className="h-8 text-xs font-mono"
            />
          </div>
        </div>

        <div className="space-y-1 text-xs">
          <label htmlFor="drift-content" className="font-medium text-foreground">
            记忆正文 (Memory Content)
          </label>
          <Textarea
            id="drift-content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={3}
            placeholder="输入包含代码文件或符号引用的经验记忆正文..."
            className="text-xs resize-none"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button
            size="sm"
            onClick={handleSingleCheck}
            disabled={loading || !content.trim()}
            className="text-xs h-8"
          >
            {loading ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <FileSearch className="mr-1.5 h-3.5 w-3.5" />
            )}
            校验单项真实性
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleBatchCheck}
            disabled={batchLoading}
            className="text-xs h-8"
          >
            {batchLoading ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Layers className="mr-1.5 h-3.5 w-3.5" />
            )}
            执行批量探针沙盒
          </Button>
        </div>

        <DriftReferenceAuditView singleResult={singleResult} batchResult={batchResult} />
      </CardContent>
    </Card>
  );
}
