import React, { useState } from 'react';
import {
  Sparkles,
  LayoutGrid,
  Activity,
  Layers,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  type MotionPersonality,
  MOTION_PERSONALITIES,
  MOTION_STACK_LANES,
  SPATIAL_GRID_SPACINGS,
  validateGpuMotionSafety,
} from './springPhysicsTokens';
import { InteractiveSpringButton } from './InteractiveSpringButton';
import { SpringCard } from './SpringCard';

export function DesignSystemGridGuide() {
  const [activePersonality, setActivePersonality] = useState<MotionPersonality>('premium');
  const [clickCount, setClickCount] = useState(0);

  const testSafety = validateGpuMotionSafety(['transform', 'opacity', 'filter']);
  const currentConfig = MOTION_PERSONALITIES[activePersonality];

  return (
    <section
      aria-label="微交互物理弹簧与设计系统规范看板"
      className="p-6 rounded-2xl border border-border bg-card/60 space-y-6 text-foreground"
    >
      {/* 头部标题与简介 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <h3 className="text-lg font-bold tracking-tight">
              动效物理学 (Spring Physics) 与微交互设计规范
            </h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            自然阻尼物理曲线 SSOT · 四大品牌动效人格 · 五车道选型矩阵 · 4px/8px 空间网格
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>GPU 合成属性门禁合规</span>
          </span>
        </div>
      </div>

      {/* 动效人格交互体验区 */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Activity className="w-4 h-4 text-primary" />
          <span>四大品牌动效人格实时体验 (当前: {currentConfig.displayName})</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {(Object.keys(MOTION_PERSONALITIES) as MotionPersonality[]).map((key) => {
            const p = MOTION_PERSONALITIES[key];
            const isSelected = activePersonality === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setActivePersonality(key);
                }}
                className={`p-3 rounded-lg border text-left transition-colors select-none cursor-pointer ${
                  isSelected
                    ? 'bg-primary/10 border-primary text-primary font-medium'
                    : 'bg-background hover:bg-muted text-muted-foreground border-border/80'
                }`}
              >
                <div className="text-xs font-bold">{p.displayName}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {p.durationMs}ms · {p.overshootPercent}% 过冲
                </div>
              </button>
            );
          })}
        </div>

        {/* 交互按钮试用 */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <InteractiveSpringButton
            variant="primary"
            personality={activePersonality}
            icon={<Zap className="w-4 h-4" />}
            onClick={() => {
              setClickCount((c) => c + 1);
            }}
          >
            弹性触觉按钮 (已点击 {clickCount} 次)
          </InteractiveSpringButton>

          <InteractiveSpringButton
            variant="outline"
            personality={activePersonality}
          >
            次级线性按钮
          </InteractiveSpringButton>

          <InteractiveSpringButton
            variant="secondary"
            personality={activePersonality}
            disabled
          >
            禁用状态 (无障碍降级)
          </InteractiveSpringButton>
        </div>
      </div>

      {/* 弹性卡片与网格展示 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SpringCard personality={activePersonality} className="p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-foreground">
            <Layers className="w-4 h-4 text-primary" />
            <span>SpringCard 物理悬停卡片</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            悬停时产生 1.5px 的物理微抬升与 1.015 细微缩放，搭配自然阻尼回弹，彻底消除生硬的 linear 或 0.3s ease 廉价感。
          </p>
        </SpringCard>

        {/* 4px/8px 空间网格自检 */}
        <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-foreground">
            <LayoutGrid className="w-4 h-4 text-primary" />
            <span>Meng To 标准 4px/8px 空间网格节奏</span>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {SPATIAL_GRID_SPACINGS.map((spacing) => (
              <span
                key={spacing.px}
                className="px-2 py-0.5 rounded bg-background border border-border/80 text-[11px] font-mono text-muted-foreground"
              >
                {spacing.px}px ({spacing.tailwind})
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 五车道选型矩阵清单 */}
      <div className="space-y-2 pt-2">
        <div className="text-xs font-semibold text-muted-foreground">
          五车道动效技术栈智能选型矩阵
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {Object.values(MOTION_STACK_LANES).slice(0, 3).map((lane) => (
            <div
              key={lane.lane}
              className="p-3 rounded-lg border border-border/60 bg-background/50 space-y-1"
            >
              <div className="text-xs font-bold text-foreground">{lane.name}</div>
              <div className="text-[11px] text-primary">{lane.bundleWeight}</div>
              <p className="text-[11px] text-muted-foreground leading-snug">
                {lane.recommendation}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
