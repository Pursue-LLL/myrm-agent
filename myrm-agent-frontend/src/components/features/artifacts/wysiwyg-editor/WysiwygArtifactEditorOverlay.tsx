/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import React from 'react';
import {
  Edit3,
  Eye,
  Save,
  RotateCcw,
  Sparkles,
  Layers,
  Zap,
} from 'lucide-react';
import { useWysiwygEditorStore } from './useWysiwygEditorStore';
import { FloatingStyleToolbar } from './FloatingStyleToolbar';
import { ZeroTokenSaveBanner } from './ZeroTokenSaveBanner';

export interface WysiwygArtifactEditorOverlayProps {
  className?: string;
}

export const WysiwygArtifactEditorOverlay: React.FC<
  WysiwygArtifactEditorOverlayProps
> = ({ className = '' }) => {
  const {
    mode,
    currentHtml,
    selectedElement,
    pendingMutations,
    version,
    toggleEditMode,
    selectElement,
    updateSelectedText,
    commitZeroTokenSave,
    discardChanges,
  } = useWysiwygEditorStore();

  const isEditing = mode === 'editing';
  const hasChanges = pendingMutations.length > 0;

  const handleToggleEdit = () => {
    toggleEditMode();
  };

  const handleSimulateSelectTitle = () => {
    selectElement({
      selector: 'h2.article-title',
      tagName: 'H2',
      textContent: '飞书文档自动化处理周报',
      styles: {
        color: '#6366f1',
        fontSize: '18px',
      },
    });
  };

  const handleSimulateInlineTextChange = (newText: string) => {
    updateSelectedText(newText);
  };

  return (
    <div
      data-testid="wysiwyg-artifact-editor-overlay"
      className={`relative flex flex-col w-full max-w-4xl mx-auto rounded-3xl bg-zinc-900/95 border border-zinc-800 shadow-2xl font-sans text-zinc-100 overflow-hidden ${className}`}
    >
      {/* 1. 顶部操作栏 */}
      <header className="flex items-center justify-between p-3.5 px-5 border-b border-zinc-800 bg-zinc-950/70">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-zinc-200">
                工件所见即所得双向微调
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                v{version}
              </span>
              {hasChanges && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {pendingMutations.length} 处未保存微调
                </span>
              )}
            </div>
            <p className="text-[11px] text-zinc-400">
              双击文本直接修改，浮动面板调整样式，0 Token 毫秒级就地保存
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {hasChanges && (
            <button
              type="button"
              onClick={discardChanges}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs font-medium transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>放弃</span>
            </button>
          )}

          {hasChanges && (
            <button
              type="button"
              onClick={commitZeroTokenSave}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              <span>保存微调 (0 Token)</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleToggleEdit}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              isEditing
                ? 'bg-indigo-600 text-white shadow'
                : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white'
            }`}
          >
            {isEditing ? (
              <>
                <Eye className="w-3.5 h-3.5" />
                <span>退出微调</span>
              </>
            ) : (
              <>
                <Edit3 className="w-3.5 h-3.5" />
                <span>快速微调</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* 2. 状态保存横幅挂载 */}
      <div className="p-3 pb-0">
        <ZeroTokenSaveBanner />
      </div>

      {/* 3. 浮动样式工具条挂载 */}
      {isEditing && <FloatingStyleToolbar />}

      {/* 4. 工件渲染沙箱容器 */}
      <main className="relative p-6 min-h-[280px] bg-zinc-950/60 overflow-y-auto">
        {isEditing && (
          <div className="mb-3 p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-[11px] font-mono text-indigo-300 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              微调模式已激活：点击下方元素即可唤起浮动样式板，或直接改动文字
            </span>
            <button
              type="button"
              onClick={handleSimulateSelectTitle}
              className="px-2 py-0.5 rounded bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/40 text-[10px]"
            >
              模拟选中标题
            </button>
          </div>
        )}

        {/* 交互工件节点演示区 */}
        <div
          data-testid="artifact-sandbox-content"
          className="p-5 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4"
        >
          <div
            data-testid="editable-title-node"
            className={`transition-all p-2 rounded-lg cursor-pointer ${
              selectedElement?.selector === 'h2.article-title'
                ? 'ring-2 ring-indigo-500 bg-indigo-500/10'
                : 'hover:bg-zinc-800/50'
            }`}
            onClick={handleSimulateSelectTitle}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSimulateSelectTitle();
              }
            }}
          >
            <h2
              className="text-base font-bold text-zinc-100"
              style={{
                color: selectedElement?.styles.color,
                fontSize: selectedElement?.styles.fontSize,
              }}
            >
              {selectedElement?.textContent || '飞书文档自动化处理周报'}
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              按内容方向、文章类型和使用场景自动归纳，支持一键筛选与飞书源文档下钻
            </p>
          </div>

          {/* 行内即时修改文字测试输入条（当选中标题时呈现） */}
          {isEditing && selectedElement && (
            <div className="flex items-center gap-2 p-2 rounded-xl bg-zinc-950 border border-zinc-800 text-xs">
              <span className="text-zinc-500 font-mono text-[11px]">
                行内直改文本:
              </span>
              <input
                type="text"
                value={selectedElement.textContent}
                onChange={(e) => {
                  handleSimulateInlineTextChange(e.target.value);
                }}
                className="flex-1 px-2 py-1 rounded-lg bg-zinc-900 border border-zinc-700 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800/80 text-xs text-zinc-500 font-mono">
            <span>数据源: 飞书多维表格知识库</span>
            <span>·</span>
            <span>更新频率: 实时</span>
          </div>
        </div>
      </main>
    </div>
  );
};
