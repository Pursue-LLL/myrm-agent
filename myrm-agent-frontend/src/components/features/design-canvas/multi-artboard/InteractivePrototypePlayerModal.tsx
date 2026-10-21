'use client';

import React from 'react';
import {
  X,
  RotateCcw,
  Smartphone,
  Tablet,
  Monitor,
  Maximize2,
  ChevronLeft,
  Sparkles,
  Link as LinkIcon,
} from 'lucide-react';
import { useMultiArtboardStore } from './useMultiArtboardStore';
import { DeviceFrameType, ArtboardLayer } from './multiArtboardTypes';

export const InteractivePrototypePlayerModal: React.FC = () => {
  const {
    artboards,
    playbackState,
    stopPlayback,
    navigatePlayback,
    goBackPlayback,
    startPlayback,
    setPlaybackDeviceFrame,
    togglePlaybackHotspotHints,
  } = useMultiArtboardStore();

  if (!playbackState.isPlaying) {
    return null;
  }

  const currentArtboard =
    artboards.find((ab) => ab.id === playbackState.currentArtboardId) ||
    artboards[0];

  const handleLayerClick = (layer: ArtboardLayer) => {
    if (layer.targetArtboardId) {
      navigatePlayback(layer.targetArtboardId, 'slide');
    }
  };

  const renderDeviceFrame = () => {
    const frame = playbackState.deviceFrame;

    let containerStyle: React.CSSProperties = {
      width: `${currentArtboard.width}px`,
      height: `${currentArtboard.height}px`,
    };

    let outerClassName = 'relative rounded-3xl overflow-hidden shadow-2xl transition-all duration-300';

    if (frame === 'iphone') {
      outerClassName =
        'relative rounded-[48px] border-[10px] border-slate-800 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.8)] overflow-hidden bg-slate-950 ring-1 ring-slate-700/80';
    } else if (frame === 'ipad') {
      outerClassName =
        'relative rounded-[36px] border-[14px] border-slate-800 shadow-2xl overflow-hidden bg-slate-950 ring-1 ring-slate-700/80';
      containerStyle = {
        width: `${Math.max(currentArtboard.width, 420)}px`,
        height: `${Math.max(currentArtboard.height, 600)}px`,
      };
    } else if (frame === 'desktop') {
      outerClassName =
        'relative rounded-xl border border-slate-700 shadow-2xl overflow-hidden bg-slate-950';
      containerStyle = {
        width: `${Math.max(currentArtboard.width, 560)}px`,
        height: `${Math.max(currentArtboard.height, 480)}px`,
      };
    }

    return (
      <div className={outerClassName} style={containerStyle}>
        {/* iPhone 灵动岛 / 听筒装饰 */}
        {frame === 'iphone' && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 w-28 h-5 bg-black rounded-full z-50 flex items-center justify-end px-3">
            <div className="w-2.5 h-2.5 rounded-full bg-slate-900 border border-slate-800" />
          </div>
        )}

        {/* 页面内容渲染区 */}
        <section
          aria-label={currentArtboard.title}
          className="relative w-full h-full overflow-y-auto overflow-x-hidden select-none"
        >
          {currentArtboard.layers.map((layer) => {
            const isClickable = Boolean(layer.targetArtboardId);
            const showPulse = isClickable && playbackState.showHotspotHints;

            const baseStyle: React.CSSProperties = {
              position: 'absolute',
              left: `${layer.x}px`,
              top: `${layer.y}px`,
              width: `${layer.width}px`,
              height: `${layer.height}px`,
              opacity: layer.opacity,
              zIndex: layer.zIndex,
            };

            if (layer.type === 'button') {
              return (
                <button
                  key={layer.id}
                  type="button"
                  onClick={() => { handleLayerClick(layer); }}
                  style={{
                    ...baseStyle,
                    backgroundColor: layer.backgroundColor || '#6366f1',
                    borderRadius: `${layer.borderRadius || 8}px`,
                    color: layer.color || '#ffffff',
                    fontSize: `${layer.fontSize || 14}px`,
                    fontWeight: layer.fontWeight || 'normal',
                    border: 'none',
                    cursor: isClickable ? 'pointer' : 'default',
                  }}
                  className={`flex items-center justify-center font-medium transition-all ${
                    isClickable
                      ? 'hover:opacity-90 active:scale-[0.97]'
                      : ''
                  } ${
                    showPulse
                      ? 'ring-4 ring-sky-400/60 animate-pulse'
                      : ''
                  }`}
                  title={layer.interactionTooltip || (isClickable ? `点击跳转至: ${layer.targetArtboardId}` : layer.name)}
                >
                  <span>{layer.text || layer.name}</span>
                  {isClickable && (
                    <LinkIcon className="w-3.5 h-3.5 ml-1.5 opacity-80" aria-hidden="true" />
                  )}
                </button>
              );
            }

            if (layer.type === 'text') {
              return (
                <div
                  key={layer.id}
                  role="presentation"
                  onClick={() => { handleLayerClick(layer); }}
                  style={{
                    ...baseStyle,
                    fontSize: `${layer.fontSize || 14}px`,
                    fontWeight: layer.fontWeight || 'normal',
                    color: layer.color || '#f8fafc',
                    fontFamily: layer.fontFamily,
                    cursor: isClickable ? 'pointer' : 'default',
                  }}
                  className={`flex items-center ${
                    showPulse ? 'ring-2 ring-sky-400 animate-pulse' : ''
                  }`}
                >
                  {layer.text}
                </div>
              );
            }

            if (layer.type === 'container') {
              return (
                <div
                  key={layer.id}
                  role="presentation"
                  style={{
                    ...baseStyle,
                    backgroundColor: layer.backgroundColor || '#0f172a',
                    borderRadius: `${layer.borderRadius || 16}px`,
                    border: layer.borderWidth ? `${layer.borderWidth}px solid ${layer.borderColor}` : 'none',
                  }}
                />
              );
            }

            return null;
          })}
        </section>
      </div>
    );
  };

  return (
    <dialog
      open
      aria-label="免 Token 交互原型播放器"
      className="fixed inset-0 z-50 flex flex-col w-full h-full max-w-none max-h-none m-0 p-0 border-0 bg-slate-950/95 backdrop-blur-xl animate-in fade-in duration-200"
    >
      {/* 顶部控制栏 */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={goBackPlayback}
            disabled={playbackState.historyStack.length === 0}
            className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              playbackState.historyStack.length > 0
                ? 'bg-slate-800 hover:bg-slate-700 text-slate-200'
                : 'bg-slate-900 text-slate-600 cursor-not-allowed'
            }`}
            title="返回上一页"
          >
            <ChevronLeft className="w-4 h-4" aria-hidden="true" />
            <span>返回</span>
          </button>

          <button
            type="button"
            onClick={() => { startPlayback(artboards[0]?.id); }}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition-colors"
            title="从首页重新开始播放"
          >
            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
          </button>

          <div className="h-4 w-px bg-slate-800" />

          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400">当前演示:</span>
            <span className="font-semibold text-slate-200 bg-slate-800 px-2 py-0.5 rounded">
              {currentArtboard.title}
            </span>
            <span className="text-[11px] text-slate-500 font-mono">
              (栈深: {playbackState.historyStack.length})
            </span>
          </div>
        </div>

        {/* 中间：外壳切换 */}
        <div className="flex items-center space-x-1 bg-slate-800/80 p-1 rounded-xl border border-slate-700/60">
          {(
            [
              { id: 'iphone', label: 'iPhone', icon: Smartphone },
              { id: 'ipad', label: 'iPad', icon: Tablet },
              { id: 'desktop', label: 'PC', icon: Monitor },
              { id: 'frameless', label: '无边框', icon: Maximize2 },
            ] as const
          ).map((item) => {
            const Icon = item.icon;
            const isActive = playbackState.deviceFrame === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => { setPlaybackDeviceFrame(item.id as DeviceFrameType); }}
                className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title={`切换为 ${item.label} 演示外壳`}
              >
                <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                <span className="hidden sm:inline">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* 右侧：热区提示与退出 */}
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => { togglePlaybackHotspotHints(); }}
            className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              playbackState.showHotspotHints
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            title="高亮闪烁所有可点击的交互热区按钮"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
            <span>热区指示器</span>
          </button>

          <button
            type="button"
            onClick={stopPlayback}
            className="flex items-center space-x-1 px-2.5 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-medium transition-colors"
            title="退出交互原型走查"
          >
            <X className="w-4 h-4" aria-hidden="true" />
            <span>退出演示</span>
          </button>
        </div>
      </header>

      {/* 居中交互演示舞台 */}
      <main className="flex-1 flex items-center justify-center p-6 overflow-hidden">
        {renderDeviceFrame()}
      </main>
    </dialog>
  );
};
