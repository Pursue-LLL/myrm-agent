import React from 'react';
import {
  Camera,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Download,
  Share2,
  Tag,
  Clock,
} from 'lucide-react';
import { useSkeuomorphicAppStore } from './useSkeuomorphicAppStore';
import { skeuomorphicAudioEngine } from './skeuomorphicAudioEngine';
import { formatTaskDuration } from './skeuomorphicAppEngine';

export const PolaroidArtifactAlbumDeck: React.FC = () => {
  const {
    artifacts,
    activeItemIndex,
    nextItem,
    prevItem,
  } = useSkeuomorphicAppStore();

  const currentItem = artifacts[activeItemIndex] || null;

  const handlePrintSnap = () => {
    skeuomorphicAudioEngine.playPolaroidShutter();
  };

  return (
    <div
      data-testid="polaroid-album-deck"
      className="flex flex-col items-center justify-between w-80 min-h-[480px] bg-slate-900 border border-slate-700 rounded-3xl p-6 shadow-2xl select-none"
    >
      {/* 顶部拟物化拍立得复古机身指示 */}
      <div className="w-full flex items-center justify-between pb-3 border-b border-slate-800 text-xs text-slate-400">
        <div className="flex items-center gap-1.5">
          <Camera className="w-4 h-4 text-amber-400" />
          <span className="font-semibold text-slate-200">Polaroid SnapDeck</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[11px] font-mono">
            {artifacts.length > 0 ? `${activeItemIndex + 1} / ${artifacts.length}` : '0/0'}
          </span>
          <button
            type="button"
            onClick={handlePrintSnap}
            className="p-1 rounded-full hover:bg-slate-800 text-amber-400 hover:text-amber-300 transition-colors"
            title="模拟快门冲印声"
            aria-label="拍摄并冲印"
          >
            <Sparkles className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 拍立得物理白边相纸卡片 */}
      <div className="relative my-4 w-64 bg-slate-100 rounded-lg p-3 pt-3 pb-8 shadow-xl transform hover:-rotate-1 transition-transform duration-200">
        {/* 顶部照片感光区 */}
        <div className="w-full h-48 bg-gradient-to-tr from-slate-800 via-slate-700 to-slate-900 rounded border border-slate-300/40 p-3 flex flex-col justify-between text-slate-100 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
              {currentItem?.artifactType.toUpperCase() || 'ARTIFACT'}
            </span>
            <div className="flex items-center gap-1 text-[10px] text-slate-300 font-mono">
              <Clock className="w-3 h-3" />
              <span>{currentItem ? formatTaskDuration(currentItem.durationMs) : '0s'}</span>
            </div>
          </div>

          <div className="my-auto">
            <h4 className="text-sm font-bold text-slate-100 leading-snug line-clamp-2">
              {currentItem?.taskTitle || '暂无任务快照'}
            </h4>
            <p className="mt-1 text-xs text-slate-300 line-clamp-3 leading-relaxed">
              {currentItem?.summary || '执行智能体交付任务后，产物将以拍立得快照形式留存在此'}
            </p>
          </div>

          <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-700/60 pt-1.5 font-mono">
            <span>By {currentItem?.authorAgent || 'Agent'}</span>
            <span>{currentItem?.createdAt || '2026-09-08'}</span>
          </div>
        </div>

        {/* 拍立得底部白色留白留注 */}
        <div className="mt-3 px-1 flex items-center justify-between text-slate-700">
          <div className="flex items-center gap-1 text-xs italic font-serif">
            <Tag className="w-3 h-3 text-slate-500" />
            <span className="truncate max-w-[150px]">
              {currentItem?.stageName || 'Deliverable Proof'}
            </span>
          </div>
          <span className="text-[10px] font-mono font-bold text-slate-500">
            #MYRM-{activeItemIndex + 1}
          </span>
        </div>
      </div>

      {/* 底部翻页控制与导出分享按钮 */}
      <div className="w-full flex items-center justify-between pt-3 border-t border-slate-800 text-slate-400 text-xs">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={prevItem}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            title="上一张快照"
            aria-label="上一张相片"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={nextItem}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            title="下一张快照"
            aria-label="下一张相片"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrintSnap}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition-colors"
            title="下载工件"
          >
            <Download className="w-3.5 h-3.5" />
            <span>导出相片</span>
          </button>
          <button
            type="button"
            onClick={handlePrintSnap}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            title="分享快照"
            aria-label="分享"
          >
            <Share2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
