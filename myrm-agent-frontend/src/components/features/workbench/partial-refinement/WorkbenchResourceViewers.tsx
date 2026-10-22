import React, { useState } from 'react';
import {
  FileText,
  Globe,
  Terminal,
  Code,
  RefreshCw,
  Send,
  Sparkles,
} from 'lucide-react';
import { WorkbenchTab } from './workbenchTypes';
import { useWorkbenchStore } from './useWorkbenchStore';
import { extractSelectionWithContext } from './partialRefinementEngine';

interface ViewerProps {
  tab: WorkbenchTab;
}

export const DocumentResourceViewer: React.FC<ViewerProps> = ({ tab }) => {
  const { setSelection } = useWorkbenchStore();
  const containerRef = React.useRef<HTMLElement>(null);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }

    const handleMouseUp = () => {
      if (typeof window === 'undefined') {
        return;
      }
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        return;
      }

      const selectedText = selection.toString().trim();
      if (!selectedText) {
        return;
      }

      const start = tab.content.indexOf(selectedText);
      if (start !== -1) {
        const range = extractSelectionWithContext(
          tab.content,
          start,
          start + selectedText.length
        );
        setSelection(range);
      }
    };

    el.addEventListener('mouseup', handleMouseUp);
    return () => {
      el.removeEventListener('mouseup', handleMouseUp);
    };
  }, [tab.content, setSelection]);

  const handleSimulateQuickSelect = () => {
    // 供单测与快捷演示触发
    const target = '预计在金融与政企市场保持激进扩张节奏，年度ARR增长率预计超过180%。';
    const start = tab.content.indexOf(target);
    if (start !== -1) {
      const range = extractSelectionWithContext(
        tab.content,
        start,
        start + target.length
      );
      setSelection(range);
    }
  };

  return (
    <section
      ref={containerRef}
      aria-label="文档阅读与划选编辑区"
      className="p-4 space-y-4 text-slate-100 font-sans leading-relaxed"
      data-testid="document-resource-viewer"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <span className="text-xs text-slate-400 flex items-center space-x-1.5">
          <FileText className="w-3.5 h-3.5 text-indigo-400" />
          <span>划选文档内任意段落即可唤起就地微调 Prompt</span>
        </span>
        <button
          type="button"
          onClick={handleSimulateQuickSelect}
          aria-label="快速划选测试段落"
          className="text-[10px] text-indigo-400 hover:text-indigo-300 bg-indigo-950/60 hover:bg-indigo-900/60 px-2 py-0.5 rounded border border-indigo-800/50 flex items-center space-x-1"
        >
          <Sparkles className="w-2.5 h-2.5" />
          <span>划选重点段落</span>
        </button>
      </div>

      <div className="prose prose-invert prose-xs max-w-none whitespace-pre-wrap selection:bg-indigo-600/50 selection:text-white">
        {tab.content}
      </div>
    </section>
  );
};

export const BrowserResourceViewer: React.FC<ViewerProps> = ({ tab }) => {
  const [url, setUrl] = useState(tab.content);

  return (
    <div
      className="flex flex-col h-full bg-slate-950 text-slate-200"
      data-testid="browser-resource-viewer"
    >
      {/* 浏览器地址栏 */}
      <div className="bg-slate-900 px-3 py-2 border-b border-slate-800 flex items-center space-x-2 text-xs">
        <Globe className="w-3.5 h-3.5 text-emerald-400" />
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          aria-label="沙箱浏览器地址"
          className="flex-1 bg-slate-950 px-2.5 py-1 rounded text-slate-200 font-mono text-[11px] border border-slate-800 focus:outline-none"
        />
        <button
          type="button"
          aria-label="刷新沙箱页面"
          className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
        </button>
      </div>

      {/* 拟真沙箱内嵌视窗 */}
      <div className="flex-1 p-6 flex flex-col items-center justify-center space-y-3 bg-slate-950">
        <div className="w-full max-w-md bg-slate-900/80 rounded-lg p-4 border border-slate-800 space-y-2">
          <div className="h-3.5 bg-slate-800 rounded w-1/2" />
          <div className="h-2.5 bg-slate-800/60 rounded w-full" />
          <div className="h-2.5 bg-slate-800/60 rounded w-3/4" />
        </div>
        <span className="text-[11px] text-slate-500 font-mono">
          沙箱内无头浏览器正在实时渲染当前任务界面
        </span>
      </div>
    </div>
  );
};

export const TerminalResourceViewer: React.FC<ViewerProps> = ({ tab }) => {
  const [history, setHistory] = useState(tab.content);
  const [command, setCommand] = useState('');

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim()) {
      return;
    }
    setHistory((prev) => `${prev}\n$ ${command}\n[Executed: ${command}]`);
    setCommand('');
  };

  return (
    <div
      className="flex flex-col h-full bg-slate-950 text-slate-100 font-mono text-xs p-3 space-y-2"
      data-testid="terminal-resource-viewer"
    >
      <div className="flex-1 overflow-y-auto whitespace-pre-wrap text-emerald-400 space-y-1">
        {history}
      </div>

      <form
        onSubmit={handleCommandSubmit}
        className="flex items-center space-x-2 pt-2 border-t border-slate-800"
      >
        <Terminal className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-slate-500">$</span>
        <input
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="输入沙箱 Bash 命令并回车..."
          aria-label="终端命令输入"
          className="flex-1 bg-transparent text-slate-100 text-xs focus:outline-none"
        />
        <button
          type="submit"
          aria-label="执行命令"
          className="p-1 text-slate-400 hover:text-slate-200"
        >
          <Send className="w-3 h-3" />
        </button>
      </form>
    </div>
  );
};

export const CodeResourceViewer: React.FC<ViewerProps> = ({ tab }) => {
  return (
    <div
      className="p-4 font-mono text-xs text-slate-200 bg-slate-950 overflow-x-auto"
      data-testid="code-resource-viewer"
    >
      <div className="flex items-center space-x-2 pb-2 text-slate-500 border-b border-slate-800">
        <Code className="w-3.5 h-3.5 text-amber-400" />
        <span>{tab.title}</span>
      </div>
      <pre className="pt-3 leading-relaxed selection:bg-amber-600/40 selection:text-white">
        {tab.content}
      </pre>
    </div>
  );
};

export const WorkbenchResourceViewers: React.FC<{ tab: WorkbenchTab }> = ({
  tab,
}) => {
  switch (tab.type) {
    case 'document':
      return <DocumentResourceViewer tab={tab} />;
    case 'browser':
      return <BrowserResourceViewer tab={tab} />;
    case 'terminal':
      return <TerminalResourceViewer tab={tab} />;
    case 'code':
    case 'table':
    default:
      return <CodeResourceViewer tab={tab} />;
  }
};
