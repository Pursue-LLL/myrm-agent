import React, { useEffect } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  Clock,
  Filter,
} from 'lucide-react';
import { useStarMapStore } from './useStarMapStore';
import { computeTimeBuckets } from './starMapRadialMath';
import { filterStarMapNodes } from './starMapCatalogData';

export const StarMapPlaybackController: React.FC = () => {
  const {
    nodes,
    filter,
    playback,
    setFilter,
    setPlaybackProgress,
    togglePlayback,
    setPlaybackSpeed,
  } = useStarMapStore();

  const filteredNodes = filterStarMapNodes(nodes, filter);
  const buckets = computeTimeBuckets(filteredNodes, 16);

  // 自动回放定时器驱动
  useEffect(() => {
    if (!playback.isPlaying) {
      return;
    }

    const stepMs = 50;
    const progressStep = (0.01 * playback.playbackSpeed);

    const interval = setInterval(() => {
      const nextProgress = playback.currentProgress + progressStep;
      if (nextProgress >= 1.0) {
        setPlaybackProgress(1.0);
        togglePlayback();
      } else {
        setPlaybackProgress(nextProgress);
      }
    }, stepMs);

    return () => clearInterval(interval);
  }, [playback.isPlaying, playback.currentProgress, playback.playbackSpeed, setPlaybackProgress, togglePlayback]);

  const handleReset = () => {
    setPlaybackProgress(0.0);
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setPlaybackProgress(val);
  };

  const scopeTabs = [
    { id: 'all' as const, label: '全部历程' },
    { id: 'used' as const, label: '已高频使用' },
    { id: 'learned' as const, label: '已演化学习' },
  ];

  return (
    <footer
      aria-label="星图演化回放控制器"
      className="w-full bg-slate-900 border border-slate-800 rounded-xl p-4 text-slate-100 shadow-md space-y-3"
      data-testid="star-map-playback-controller"
    >
      {/* 顶部控制栏：范围筛选与播放控件 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* 范围选项 */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
          {scopeTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setFilter({ scope: tab.id })}
              className={`px-3 py-1 rounded font-medium transition-colors ${
                filter.scope === tab.id
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 播放控制按钮 */}
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleReset}
            aria-label="重置时间游标到原点"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={togglePlayback}
            aria-label={playback.isPlaying ? '暂停回放' : '开始时间线回放'}
            className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow flex items-center space-x-1.5 transition-all"
          >
            {playback.isPlaying ? (
              <>
                <Pause className="w-3.5 h-3.5 fill-current" />
                <span>暂停</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>回放</span>
              </>
            )}
          </button>

          {/* 播放速率 */}
          <div className="flex items-center space-x-1 bg-slate-950 px-1 py-0.5 rounded border border-slate-800 text-[11px]">
            {[1, 2, 5].map((spd) => (
              <button
                key={spd}
                type="button"
                onClick={() => setPlaybackSpeed(spd)}
                className={`px-1.5 py-0.5 rounded ${
                  playback.playbackSpeed === spd
                    ? 'bg-slate-800 text-indigo-400 font-bold'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {spd}x
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 分桶直方图可视化柱状条 */}
      <div className="relative pt-2">
        <div className="flex items-end h-8 gap-1 px-1 mb-1">
          {buckets.map((b) => {
            const total = b.skillCount + b.memoryCount;
            const skillHeight = total > 0 ? (b.skillCount / Math.max(1, total)) * 100 : 0;
            const memHeight = total > 0 ? (b.memoryCount / Math.max(1, total)) * 100 : 0;

            return (
              <div
                key={b.bucketIndex}
                className="flex-1 bg-slate-800/60 rounded-t overflow-hidden h-full flex flex-col justify-end"
                title={`${b.label}: ${b.skillCount} 技能, ${b.memoryCount} 记忆`}
              >
                {b.memoryCount > 0 && (
                  <div
                    style={{ height: `${memHeight}%` }}
                    className="w-full bg-sky-500/70"
                  />
                )}
                {b.skillCount > 0 && (
                  <div
                    style={{ height: `${skillHeight}%` }}
                    className="w-full bg-amber-500/80"
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* 交互进度滑块 */}
        <input
          type="range"
          min="0"
          max="1"
          step="0.005"
          value={playback.currentProgress}
          onChange={handleSliderChange}
          aria-label="回放时间进度滑块"
          className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
        />

        {/* 时间刻度标签 */}
        <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
          <span>初创阶段 (原点)</span>
          <span className="text-slate-400 font-mono flex items-center space-x-1">
            <Clock className="w-2.5 h-2.5 text-indigo-400" />
            <span>当前截止：{new Date(playback.currentCutoffTimestamp).toLocaleDateString()}</span>
          </span>
          <span>全历程演化最新</span>
        </div>
      </div>
    </footer>
  );
};
