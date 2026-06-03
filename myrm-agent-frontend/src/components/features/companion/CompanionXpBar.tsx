import React, { useEffect, useState } from 'react';

import { IconSparkle } from '@/components/features/icons/PremiumIcons';
import useCompanionStore from '@/store/useCompanionStore';

export const CompanionXpBar: React.FC = () => {
  const { mascotLevel, mascotXp, mascotNextLevelXp, mascotUnlockedTools } = useCompanionStore();

  const [showUnlockAnimation, setShowUnlockAnimation] = useState(false);
  const [recentlyUnlocked, setRecentlyUnlocked] = useState<string | null>(null);
  const [prevLevel, setPrevLevel] = useState(mascotLevel);
  const [prevToolsCount, setPrevToolsCount] = useState(mascotUnlockedTools.length);

  useEffect(() => {
    if (mascotLevel > prevLevel || mascotUnlockedTools.length > prevToolsCount) {
      const newTool = mascotUnlockedTools[mascotUnlockedTools.length - 1];
      setRecentlyUnlocked(newTool);
      setShowUnlockAnimation(true);
      setTimeout(() => setShowUnlockAnimation(false), 4000);
    }
    setPrevLevel(mascotLevel);
    setPrevToolsCount(mascotUnlockedTools.length);
  }, [mascotLevel, mascotUnlockedTools, prevLevel, prevToolsCount]);

  const progressPercentage = Math.min(100, Math.max(0, (mascotXp / mascotNextLevelXp) * 100));

  return (
    <div className="w-full mt-4 flex flex-col items-center relative">
      <div className="flex justify-between w-full text-xs text-muted-foreground mb-1 px-1 font-semibold tracking-wider">
        <span>LVL {mascotLevel}</span>
        <span>
          {mascotXp} / {mascotNextLevelXp} XP
        </span>
      </div>

      <div className="w-full h-2 bg-muted rounded-full overflow-hidden relative shadow-inner">
        <div
          className="h-full bg-primary transition-all duration-1000 ease-out relative"
          style={{ width: `${progressPercentage}%` }}
        >
          <div className="absolute inset-0 bg-primary-foreground/20 animate-pulse" />
        </div>
      </div>

      {showUnlockAnimation && recentlyUnlocked && (
        <div className="absolute -top-12 left-1/2 transform -translate-x-1/2 bg-primary text-primary-foreground text-xs font-bold px-3 py-1 rounded-full shadow-lg animate-bounce whitespace-nowrap z-50 flex items-center gap-1">
          <IconSparkle className="size-3" />
          Unlocked: {recentlyUnlocked}
          <IconSparkle className="size-3" />
        </div>
      )}
    </div>
  );
};
