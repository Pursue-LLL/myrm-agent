/**
 * Bidi Typography Shield Card Component
 * 全球化双向文本排版防护与 Windows 复杂多语系字体防御交互式卡片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范与对比视图设计；
 * 5. 行数严格受控在 400 行以内。
 */

import React, { useMemo } from 'react';
import {
  AlignLeft,
  AlignRight,
  Check,
  Globe2,
  Languages,
  RotateCcw,
  Shield,
  ShieldCheck,
  Type,
} from 'lucide-react';
import { BidiIsolatedText } from './BidiIsolatedText';
import {
  detectTextDirection,
  WINDOWS_RTL_SAFE_FONT_STACK,
} from './bidiDetectorEngine';
import { TextDirection } from './bidiShieldTypes';
import { useBidiShieldStore } from './useBidiShieldStore';

export interface BidiTypographyShieldCardProps {
  className?: string;
}

export const BidiTypographyShieldCard: React.FC<
  BidiTypographyShieldCardProps
> = ({ className = '' }) => {
  const {
    direction,
    isWindowsTypographyShieldActive,
    customInputText,
    samplePresets,
    setDirection,
    toggleWindowsTypographyShield,
    setCustomInputText,
    loadPreset,
    resetToDefault,
  } = useBidiShieldStore();

  const detection = useMemo(() => {
    return detectTextDirection(customInputText);
  }, [customInputText]);

  const effectiveDirection: 'ltr' | 'rtl' =
    direction === 'auto' ? detection.dominantDirection : direction;

  return (
    <div
      data-testid="bidi-typography-shield-card"
      className={`flex flex-col gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-5 text-neutral-100 ${className}`}
    >
      {/* 头部：标题、方向徽标与 Windows 字体加固开关 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/80 pb-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-950/40 text-indigo-400">
            <Languages className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-neutral-100">
                双向文本自动隔离与 Windows 字体防御
              </h3>
              <span
                data-testid="effective-direction-badge"
                className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-medium font-mono text-indigo-300"
              >
                {effectiveDirection === 'rtl' ? (
                  <AlignRight className="h-3 w-3" />
                ) : (
                  <AlignLeft className="h-3 w-3" />
                )}
                <span>方向: {effectiveDirection.toUpperCase()}</span>
              </span>
            </div>
            <p className="text-xs text-neutral-400">
              采用 CSS 逻辑属性与 &lt;bdi&gt; 隔离，彻底消除混合代码时标点倒错与 Windows 字体乱码
            </p>
          </div>
        </div>

        {/* 控制区：方向模式切换与 Windows 字体防御开关 */}
        <div className="flex items-center gap-2 text-xs">
          <div className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 p-0.5">
            {(['auto', 'ltr', 'rtl'] as TextDirection[]).map((dirMode) => (
              <button
                key={dirMode}
                type="button"
                onClick={() => {
                  setDirection(dirMode);
                }}
                data-testid={`direction-mode-btn-${dirMode}`}
                className={`rounded px-2 py-1 text-xs transition-colors ${
                  direction === dirMode
                    ? 'bg-indigo-950 font-medium text-indigo-300'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {dirMode === 'auto' ? '自动检测' : dirMode.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={toggleWindowsTypographyShield}
            data-testid="toggle-windows-shield-btn"
            className={`flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs transition-colors ${
              isWindowsTypographyShieldActive
                ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-300'
                : 'border-neutral-800 bg-neutral-900 text-neutral-400 hover:text-neutral-200'
            }`}
            title="切换 Windows DirectWrite 跨语系稳健字体回退栈"
          >
            {isWindowsTypographyShieldActive ? (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <Shield className="h-3.5 w-3.5 text-neutral-500" />
            )}
            <span>Windows 字体加固</span>
          </button>

          <button
            type="button"
            onClick={resetToDefault}
            data-testid="reset-bidi-btn"
            className="rounded p-1 text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
            title="重置测试配置"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 预设用例快速切换 */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-neutral-500 text-[11px]">快速测试预设:</span>
        {samplePresets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => {
              loadPreset(preset.id);
            }}
            data-testid={`load-preset-btn-${preset.id}`}
            className="rounded border border-neutral-800 bg-neutral-900/80 px-2.5 py-1 text-xs text-neutral-300 hover:border-indigo-500/50 hover:bg-indigo-950/30 transition-colors"
          >
            {preset.title}
          </button>
        ))}
      </div>

      {/* 实时输入编辑区 */}
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex items-center justify-between text-neutral-400">
          <label htmlFor="bidi-test-input" className="text-[11px]">
            双向混合测试文本（支持阿拉伯语/希伯来语/代码片段）:
          </label>
          <span className="font-mono text-[10px] text-neutral-500">
            RTL 字符占比: {(detection.rtlRatio * 100).toFixed(1)}% ({detection.segments.length} 个隔离分段)
          </span>
        </div>
        <textarea
          id="bidi-test-input"
          rows={2}
          value={customInputText}
          onChange={(e) => {
            setCustomInputText(e.target.value);
          }}
          className="w-full rounded-md border border-neutral-800 bg-neutral-900 p-2.5 text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      {/* 对比展示工作区：普通未隔离 vs Bidi 隔离加固 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* 左侧：旧版常规渲染（无隔离保护） */}
        <div className="flex flex-col rounded-lg border border-neutral-800/80 bg-neutral-900/40 p-3.5">
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-2 mb-2 text-neutral-400">
            <span className="font-medium">普通文本渲染 (未隔离基准)</span>
            <span className="text-[10px] text-rose-400">标点与代码易错位</span>
          </div>

          <div
            data-testid="unshielded-text-preview"
            dir={effectiveDirection}
            className="flex-1 break-words text-neutral-300 leading-relaxed font-sans"
          >
            {customInputText}
          </div>
        </div>

        {/* 右侧：BidiIsolatedText 加固防护渲染 */}
        <div className="flex flex-col rounded-lg border border-indigo-500/40 bg-indigo-950/20 p-3.5 shadow-sm">
          <div className="flex items-center justify-between border-b border-indigo-500/30 pb-2 mb-2">
            <span className="font-medium text-indigo-300 flex items-center gap-1">
              <Check className="h-3 w-3 text-emerald-400" />
              <span>Bidi 隔离与字体回退加固</span>
            </span>
            <span className="text-[10px] font-mono text-indigo-400">
              &lt;bdi&gt; isolate
            </span>
          </div>

          <BidiIsolatedText
            text={customInputText}
            dir={effectiveDirection}
            className="flex-1 break-words text-neutral-100 leading-relaxed"
          />
        </div>
      </div>

      {/* 底部：当前生效的字体栈与 CSS 逻辑属性状态说明 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-800/60 pt-2.5 text-[11px] text-neutral-500">
        <div className="flex items-center gap-1.5 font-mono">
          <Type className="h-3 w-3 text-indigo-400" />
          <span>生效字体栈:</span>
          <span className="truncate max-w-[340px] text-neutral-400">
            {isWindowsTypographyShieldActive
              ? WINDOWS_RTL_SAFE_FONT_STACK
              : '默认系统字体'}
          </span>
        </div>

        <div className="flex items-center gap-1 font-mono text-emerald-400/90">
          <Globe2 className="h-3 w-3" />
          <span>采用 CSS 逻辑属性 (padding-inline-start / margin-inline)</span>
        </div>
      </div>
    </div>
  );
};
