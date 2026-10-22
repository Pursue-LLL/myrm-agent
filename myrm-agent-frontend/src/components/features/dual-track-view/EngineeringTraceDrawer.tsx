/**
 * EngineeringTraceDrawer.tsx
 * 底层工程追踪侧边抽屉：展示完整的代码 Diff、ToolCall 列表、终端运行日志与物理测试断言
 */

import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  Code2,
  FileCode,
  Terminal,
  Wrench,
  X,
  XCircle,
} from 'lucide-react';
import {
  formatTraceSummaryBadge,
  summarizeEngineeringTrace,
} from './dualTrackEngine';
import { useDualTrackStore } from './useDualTrackStore';

export interface EngineeringTraceDrawerProps {
  className?: string;
  onClose?: () => void;
}

type TraceTab = 'tools' | 'diffs' | 'terminal' | 'tests';

export const EngineeringTraceDrawer: React.FC<EngineeringTraceDrawerProps> = ({
  className = '',
  onClose,
}) => {
  const isTraceDrawerOpen = useDualTrackStore(
    (state) => state.isTraceDrawerOpen
  );
  const activeTraceDetails = useDualTrackStore(
    (state) => state.activeTraceDetails
  );
  const closeTraceDrawer = useDualTrackStore((state) => state.closeTraceDrawer);

  const [activeTab, setActiveTab] = useState<TraceTab>('tools');

  const traceSummary = useMemo(() => {
    return summarizeEngineeringTrace(activeTraceDetails ?? undefined);
  }, [activeTraceDetails]);

  const summaryBadge = useMemo(() => {
    return formatTraceSummaryBadge(traceSummary);
  }, [traceSummary]);

  if (!isTraceDrawerOpen || activeTraceDetails === null) {
    return null;
  }

  const handleClose = (): void => {
    closeTraceDrawer();
    if (onClose !== undefined) {
      onClose();
    }
  };

  return (
    <aside
      data-testid="engineering-trace-drawer"
      aria-label="底层工程追踪抽屉"
      className={`fixed inset-y-0 right-0 w-full max-w-lg bg-slate-900 border-l border-slate-700/80 shadow-2xl z-50 flex flex-col text-slate-200 ${className}`}
    >
      {/* 头部导航与关闭 */}
      <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/70">
        <div className="flex items-center gap-2">
          <Wrench className="w-5 h-5 text-blue-400" />
          <div>
            <h2 className="text-sm font-semibold">
              底层工程执行细节
            </h2>
            <p className="text-[10px] text-slate-400 mt-0.5">
              {summaryBadge}
            </p>
          </div>
        </div>

        <button
          type="button"
          data-testid="close-trace-drawer-btn"
          aria-label="关闭工程追踪抽屉"
          onClick={handleClose}
          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tab 导航切换 */}
      <div className="flex items-center border-b border-slate-800 px-3 bg-slate-950/40 text-xs">
        <button
          type="button"
          data-testid="tab-tools-btn"
          onClick={() => setActiveTab('tools')}
          className={`flex items-center gap-1.5 px-3 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === 'tools'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Wrench className="w-3.5 h-3.5" />
          <span>工具调用 ({traceSummary.toolCount})</span>
        </button>

        <button
          type="button"
          data-testid="tab-diffs-btn"
          onClick={() => setActiveTab('diffs')}
          className={`flex items-center gap-1.5 px-3 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === 'diffs'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Code2 className="w-3.5 h-3.5" />
          <span>代码变更 ({traceSummary.diffCount})</span>
        </button>

        <button
          type="button"
          data-testid="tab-terminal-btn"
          onClick={() => setActiveTab('terminal')}
          className={`flex items-center gap-1.5 px-3 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === 'terminal'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>终端命令 ({traceSummary.logLineCount})</span>
        </button>

        <button
          type="button"
          data-testid="tab-tests-btn"
          onClick={() => setActiveTab('tests')}
          className={`flex items-center gap-1.5 px-3 py-2.5 font-medium border-b-2 transition-colors ${
            activeTab === 'tests'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>测试断言 ({activeTraceDetails.testAssertions.length})</span>
        </button>
      </div>

      {/* 主面板内容区 */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        {/* 工具调用面板 */}
        {activeTab === 'tools' && (
          <div data-testid="trace-tools-panel" className="flex flex-col gap-2.5">
            {activeTraceDetails.toolCalls.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">
                本轮无工具调用
              </div>
            ) : (
              activeTraceDetails.toolCalls.map((tool) => (
                <div
                  key={tool.id}
                  data-testid={`tool-call-item-${tool.id}`}
                  className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col gap-1.5 text-xs"
                >
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-blue-400">
                      {tool.toolName}
                    </span>
                    {tool.durationMs !== undefined && (
                      <span className="text-[10px] text-slate-500">
                        {tool.durationMs}ms
                      </span>
                    )}
                  </div>
                  <div className="text-slate-300 font-mono text-[11px] bg-slate-900 p-2 rounded border border-slate-800/80">
                    {tool.inputSummary}
                  </div>
                  {tool.outputPreview !== undefined && (
                    <div className="text-slate-400 text-[10px] truncate">
                      输出: {tool.outputPreview}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* 代码变更 Diff 面板 */}
        {activeTab === 'diffs' && (
          <div data-testid="trace-diffs-panel" className="flex flex-col gap-3">
            {activeTraceDetails.codeDiffs.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">
                本轮无代码修改
              </div>
            ) : (
              activeTraceDetails.codeDiffs.map((diff, idx) => (
                <div
                  key={idx}
                  data-testid={`code-diff-item-${idx}`}
                  className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden text-xs font-mono"
                >
                  <div className="flex items-center justify-between px-3 py-2 bg-slate-900 border-b border-slate-800">
                    <span className="flex items-center gap-1.5 text-slate-200">
                      <FileCode className="w-3.5 h-3.5 text-blue-400" />
                      <span>{diff.filePath}</span>
                    </span>
                    <span className="text-[10px] text-slate-400">
                      <span className="text-emerald-400">+{diff.additions}</span>{' '}
                      <span className="text-red-400">-{diff.deletions}</span>
                    </span>
                  </div>
                  <pre className="p-3 overflow-x-auto text-[11px] text-slate-300 leading-relaxed">
                    {diff.diffText}
                  </pre>
                </div>
              ))
            )}
          </div>
        )}

        {/* 终端命令日志面板 */}
        {activeTab === 'terminal' && (
          <div
            data-testid="trace-terminal-panel"
            className="flex-1 bg-slate-950 rounded-xl p-3 border border-slate-800 font-mono text-[11px] text-slate-300 overflow-auto flex flex-col gap-1"
          >
            {activeTraceDetails.terminalLogs.length === 0 ? (
              <span className="text-slate-500">无终端命令输出日志</span>
            ) : (
              activeTraceDetails.terminalLogs.map((log, index) => (
                <div key={index} className="leading-relaxed">
                  <span className="text-slate-600 mr-2">$</span>
                  <span>{log}</span>
                </div>
              ))
            )}
          </div>
        )}

        {/* 测试断言结果面板 */}
        {activeTab === 'tests' && (
          <div data-testid="trace-tests-panel" className="flex flex-col gap-2">
            {activeTraceDetails.testAssertions.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-8">
                本轮无测试断言执行记录
              </div>
            ) : (
              activeTraceDetails.testAssertions.map((test) => (
                <div
                  key={test.id}
                  data-testid={`test-assertion-item-${test.id}`}
                  className="p-2.5 rounded-xl bg-slate-950/70 border border-slate-800 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    {test.passed ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400" />
                    )}
                    <span className="font-mono text-slate-200">
                      {test.testName}
                    </span>
                  </div>
                  <span
                    className={`text-[10px] font-bold ${
                      test.passed ? 'text-emerald-400' : 'text-red-400'
                    }`}
                  >
                    {test.passed ? 'PASS' : 'FAIL'}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
