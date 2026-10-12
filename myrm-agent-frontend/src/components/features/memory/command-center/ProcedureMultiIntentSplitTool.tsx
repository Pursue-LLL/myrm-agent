'use client';

/**
 * [INPUT]
 * None
 *
 * [OUTPUT]
 * ProcedureMultiIntentSplitTool: Subcomponent providing split-over-merge multi-intent decomposition.
 *
 * [POS]
 * Subcomponent for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 150 lines.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Scissors, X, Tag } from 'lucide-react';

interface ProcedureMultiIntentSplitToolProps {
  isOpen: boolean;
  onClose: () => void;
  onSplitIntents: (rawText: string) => Promise<Array<{ intent: string; body: string }>>;
}

export function ProcedureMultiIntentSplitTool({
  isOpen,
  onClose,
  onSplitIntents,
}: ProcedureMultiIntentSplitToolProps): React.JSX.Element | null {
  const [splitInput, setSplitInput] = useState<string>(
    'Intent 1: 检查代码仓库依赖冲突并更新 package.json\n先运行 bun outdated，然后对比锁定版本，最后更新依赖。\nIntent 2: 构建生产包并部署到测试集群\n先运行 bun run build，然后生成 Docker 镜像并推送到镜像仓库。'
  );
  const [splitResults, setSplitResults] = useState<Array<{ intent: string; body: string }>>([]);
  const [isSplitting, setIsSplitting] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleRunSplit = async () => {
    if (!splitInput.trim()) return;
    setIsSplitting(true);
    try {
      const fragments = await onSplitIntents(splitInput);
      setSplitResults(fragments);
    } finally {
      setIsSplitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-text-primary text-xs flex items-center gap-1.5">
          <Scissors className="h-4 w-4 text-primary" />
          多意图强制拆解引擎 (Split-over-Merge)
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-text-secondary hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-primary rounded"
          aria-label="关闭拆条工具"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <p className="text-text-secondary text-xs">
        原则：非 EXACT 相同意图同工具序列绝不合并；单会话包含多阶段或生命周期转换必须拆解为单意图经验。
      </p>

      <textarea
        value={splitInput}
        onChange={(e) => setSplitInput(e.target.value)}
        rows={3}
        className="w-full rounded-md border border-border-subtle bg-surface p-2.5 font-mono text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
        placeholder="粘贴包含多个 Intent 的复合执行记录..."
        aria-label="复合执行记录文本"
      />

      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          onClick={handleRunSplit}
          disabled={isSplitting || !splitInput.trim()}
          className="bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {isSplitting ? '拆解中...' : '执行强制拆解'}
        </Button>
      </div>

      {splitResults.length > 0 && (
        <div className="mt-2 space-y-2 border-t border-primary/10 pt-2">
          <span className="text-[11px] font-medium text-text-primary">
            拆解生成 {splitResults.length} 个独立意图片段:
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {splitResults.map((frag, idx) => (
              <div key={idx} className="rounded-lg border border-border-subtle bg-surface p-2.5 text-xs space-y-1">
                <div className="font-semibold text-primary flex items-center gap-1">
                  <Tag className="h-3 w-3" />
                  {frag.intent}
                </div>
                <p className="text-text-secondary text-[11px] line-clamp-2">{frag.body}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
