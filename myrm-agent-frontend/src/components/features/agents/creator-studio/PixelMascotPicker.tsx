import React from 'react';
import {
  Sparkles,
  Bot,
  Cat,
  Dog,
  Bird,
  Flame,
  Wand2,
  Loader2,
  Check,
} from 'lucide-react';
import type { AvatarSourceType, PixelMascot } from './botCreatorStudioTypes';

interface PixelMascotPickerProps {
  availableMascots: PixelMascot[];
  selectedMascotId: string;
  avatarType: AvatarSourceType;
  isGeneratingAvatar: boolean;
  generatedAvatarUrl?: string;
  onSelectMascot: (mascotId: string) => void;
  onGenerateAvatar: () => void;
}

const MASCOT_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Cat,
  Dog,
  Bird,
  Flame,
  Bot,
  Sparkles,
};

export const PixelMascotPicker: React.FC<PixelMascotPickerProps> = ({
  availableMascots,
  selectedMascotId,
  avatarType,
  isGeneratingAvatar,
  generatedAvatarUrl,
  onSelectMascot,
  onGenerateAvatar,
}) => {
  return (
    <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-1.5">
          <Sparkles className="h-4 w-4 text-amber-400" />
          <span className="text-xs font-semibold text-slate-100">
            视觉标识与像素吉祥物
          </span>
          <span className="rounded bg-amber-500/10 px-1.5 py-0.2 text-[10px] font-medium text-amber-300">
            赋能人格化陪伴
          </span>
        </div>
        <button
          type="button"
          onClick={onGenerateAvatar}
          disabled={isGeneratingAvatar}
          className="inline-flex items-center space-x-1.5 rounded-md bg-purple-600/80 px-2.5 py-1 text-xs font-medium text-white shadow-sm hover:bg-purple-500 disabled:opacity-50"
          aria-label="根据人设一键生图"
        >
          {isGeneratingAvatar ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>生图中...</span>
            </>
          ) : (
            <>
              <Wand2 className="h-3 w-3" />
              <span>根据人设 AI 一键生图</span>
            </>
          )}
        </button>
      </div>

      {avatarType === 'ai_generated' && generatedAvatarUrl && (
        <div className="flex items-center justify-between rounded-lg border border-purple-500/40 bg-purple-950/20 p-2.5 text-xs text-purple-200">
          <div className="flex items-center space-x-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-900/60 border border-purple-400">
              <Sparkles className="h-5 w-5 text-purple-300" />
            </div>
            <div>
              <div className="font-semibold text-slate-100">AI 定制头像生成完毕</div>
              <p className="text-[11px] text-slate-400">已根据当前 SOUL.md 人设渲染出专属标识</p>
            </div>
          </div>
          <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] text-purple-300">
            当前生效
          </span>
        </div>
      )}

      <div>
        <div className="text-[11px] text-slate-400 mb-2">或从复古像素电子宠物库中秒级选用:</div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {availableMascots.map((mascot) => {
            const Icon = MASCOT_ICON_MAP[mascot.iconName] ?? Bot;
            const isSelected = avatarType === 'pixel_mascot' && selectedMascotId === mascot.id;

            return (
              <button
                key={mascot.id}
                type="button"
                onClick={() => {
                  onSelectMascot(mascot.id);
                }}
                className={`relative flex flex-col items-center justify-center rounded-lg border p-2 transition-all ${
                  isSelected
                    ? 'border-amber-400/80 bg-amber-950/30 shadow-[0_0_10px_rgba(251,191,36,0.2)]'
                    : 'border-slate-800 bg-slate-850/60 hover:border-slate-700 hover:bg-slate-800'
                }`}
              >
                {isSelected && (
                  <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-400 text-slate-950">
                    <Check className="h-2.5 w-2.5 stroke-[3]" />
                  </span>
                )}
                <div className={`p-1.5 ${mascot.colorClass}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <span className="mt-1 text-[10px] font-medium text-slate-300 truncate w-full text-center">
                  {mascot.name}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
