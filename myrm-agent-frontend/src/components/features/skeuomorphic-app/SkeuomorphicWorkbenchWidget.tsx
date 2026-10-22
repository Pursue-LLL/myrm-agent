import React from 'react';
import {
  Disc,
  Camera,
  Volume2,
  VolumeX,
  Minimize2,
  Maximize2,
  Vibrate,
  Sliders,
} from 'lucide-react';
import { useSkeuomorphicAppStore } from './useSkeuomorphicAppStore';
import { ClassicIpodTaskCarouselPlayer } from './ClassicIpodTaskCarouselPlayer';
import { PolaroidArtifactAlbumDeck } from './PolaroidArtifactAlbumDeck';
import { SkeuomorphicSkinType } from './skeuomorphicTypes';

export const SkeuomorphicWorkbenchWidget: React.FC = () => {
  const {
    activeSkin,
    soundEnabled,
    hapticEnabled,
    isMinimized,
    artifacts,
    activeItemIndex,
    setActiveSkin,
    toggleSound,
    toggleHaptic,
    toggleMinimized,
  } = useSkeuomorphicAppStore();

  const currentItem = artifacts[activeItemIndex] || null;

  const handleSkinChange = (skin: SkeuomorphicSkinType) => {
    setActiveSkin(skin);
  };

  if (isMinimized) {
    return (
      <div
        data-testid="skeuomorphic-minimized-pill"
        className="fixed bottom-6 right-6 z-40 flex items-center gap-3 bg-slate-900/95 backdrop-blur border border-slate-700 text-slate-200 px-4 py-2.5 rounded-full shadow-2xl select-none animate-in fade-in slide-in-from-bottom-2 duration-150"
      >
        <div className="flex items-center gap-2">
          {activeSkin === 'classic_ipod' ? (
            <Disc className="w-4 h-4 text-emerald-400 animate-spin" />
          ) : (
            <Camera className="w-4 h-4 text-amber-400" />
          )}
          <span className="text-xs font-semibold max-w-[140px] truncate">
            {currentItem?.taskTitle || '任务工件播放器'}
          </span>
        </div>
        <div className="h-3.5 w-px bg-slate-700" />
        <button
          type="button"
          onClick={toggleMinimized}
          className="p-1 rounded-full hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          title="展开拟物化工作台挂件"
          aria-label="展开挂件"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="skeuomorphic-workbench-widget"
      className="relative flex flex-col items-center bg-slate-950/80 backdrop-blur-md border border-slate-800 rounded-3xl p-4 shadow-2xl"
    >
      {/* 顶部拟物化控制条 */}
      <div className="w-full flex items-center justify-between pb-3 mb-2 border-b border-slate-800/80 text-xs text-slate-300">
        {/* 拟物化皮肤选择器 */}
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5">
          <button
            type="button"
            onClick={() => handleSkinChange('classic_ipod')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              activeSkin === 'classic_ipod'
                ? 'bg-slate-800 text-emerald-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="经典 iPod 滚轮任务播放器"
          >
            <Disc className="w-3.5 h-3.5" />
            <span>iPod</span>
          </button>
          <button
            type="button"
            onClick={() => handleSkinChange('polaroid_album')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              activeSkin === 'polaroid_album'
                ? 'bg-slate-800 text-amber-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="拍立得冲印任务相册"
          >
            <Camera className="w-3.5 h-3.5" />
            <span>Polaroid</span>
          </button>
        </div>

        {/* 右侧音效与触感控制按钮 */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggleSound}
            className={`p-1.5 rounded-lg border transition-colors ${
              soundEnabled
                ? 'bg-slate-900 border-slate-700 text-emerald-400'
                : 'bg-slate-900/50 border-slate-800 text-slate-500'
            }`}
            title={soundEnabled ? '音效已开启' : '音效已静音'}
            aria-label="切换声音"
          >
            {soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={toggleHaptic}
            className={`p-1.5 rounded-lg border transition-colors ${
              hapticEnabled
                ? 'bg-slate-900 border-slate-700 text-amber-400'
                : 'bg-slate-900/50 border-slate-800 text-slate-500'
            }`}
            title={hapticEnabled ? '物理触感震动已开启' : '触感已禁用'}
            aria-label="切换触感"
          >
            <Vibrate className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={toggleMinimized}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition-colors"
            title="最小化挂件"
            aria-label="最小化"
          >
            <Minimize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 主体渲染区 */}
      <div className="mt-1">
        {activeSkin === 'classic_ipod' ? (
          <ClassicIpodTaskCarouselPlayer />
        ) : (
          <PolaroidArtifactAlbumDeck />
        )}
      </div>

      {/* 底部架构克制与 JIT 提示 */}
      <div className="w-full mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
        <div className="flex items-center gap-1">
          <Sliders className="w-3 h-3 text-slate-600" />
          <span>JIT Skeuomorphic Visualizer</span>
        </div>
        <span>Framer Motion & Web Audio</span>
      </div>
    </div>
  );
};
