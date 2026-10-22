/**
 * [INPUT]
 * - onSelectPrompt?: (prompt: string) => void
 *
 * [OUTPUT]
 * - QuickDelightLane: Lightweight inspiration lane embedded on EmptyChat welcome page
 *
 * [POS]
 * Client-side component for Zero-Code Hobbyist Delight Inspiration Lane (Item 40 P0).
 * Strictly under 160 lines. Zero `any`.
 */

import React from "react";
import { Sparkles, Cake, Calendar, Disc, Star, ArrowRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { useDelightShowcaseStore } from "./useDelightShowcaseStore";

interface QuickDelightLaneProps {
  onSelectPrompt?: (prompt: string) => void;
}

const FEATURED_CHIPS = [
  {
    id: "chip_bday",
    title: "程序员土味生日烟花",
    prompt: "做一个给程序员庆祝生日的单文件 HTML，带黑客帝国字符雨背景、Canvas 烟花动画和打字机土味祝福语",
    icon: Cake,
  },
  {
    id: "chip_anni",
    title: "纪念日甜蜜倒计时",
    prompt: "做一个温馨高颜值的纪念日倒计时单文件网页，带渐变卡片、心跳动效和天时分秒实时计算",
    icon: Calendar,
  },
  {
    id: "chip_wheel",
    title: "聚餐吃什么？命运大转盘",
    prompt: "做一个聚餐决策大转盘单文件网页，带 Canvas 绘制彩色扇区、阻尼减速旋转动效和弹窗结果",
    icon: Disc,
  },
  {
    id: "chip_meteor",
    title: "夜空星语流星瓶",
    prompt: "做一个流星雨夜空心愿瓶交互，点击屏幕划过流星，支持输入心愿并保存在瓶子卡片中",
    icon: Star,
  },
];

export const QuickDelightLane: React.FC<QuickDelightLaneProps> = ({ onSelectPrompt }) => {
  const t = useTranslations("delightShowcase");
  const setGalleryOpen = useDelightShowcaseStore((state) => state.setGalleryOpen);

  const handleChipClick = (prompt: string) => {
    if (onSelectPrompt) {
      onSelectPrompt(prompt);
    } else {
      setGalleryOpen(true);
    }
  };

  return (
    <section
      aria-label={t("quickLaneTitle")}
      className="w-full max-w-2xl mx-auto my-3 px-3 py-2.5 rounded-xl bg-gradient-to-r from-amber-500/10 via-rose-500/10 to-indigo-500/10 border border-amber-500/20 backdrop-blur-sm"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
          <Sparkles className="w-3.5 h-3.5 text-amber-400" />
          <span>{t("quickLaneTitle")}</span>
        </div>
        <button
          type="button"
          onClick={() => setGalleryOpen(true)}
          className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-amber-300 transition-colors"
        >
          <span>{t("allCategories")}</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {FEATURED_CHIPS.map((chip) => {
          const Icon = chip.icon;
          return (
            <button
              key={chip.id}
              type="button"
              onClick={() => handleChipClick(chip.prompt)}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-700/60 hover:border-amber-500/50 text-zinc-200 transition-all shadow-sm active:scale-95"
            >
              <Icon className="w-3 h-3 text-amber-400 flex-shrink-0" />
              <span className="truncate max-w-[140px]">{chip.title}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
};
