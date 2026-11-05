'use client';

import { useTranslations } from 'next-intl';

/** 更新日志分组列表：默认各展示 5 条，超出部分由「显示更多」展开。 */

interface StackUpdateChangelogProps {
  fixed: string[];
  other: string[];
  expanded: boolean;
  onToggleExpanded: () => void;
}

export default function StackUpdateChangelog({ fixed, other, expanded, onToggleExpanded }: StackUpdateChangelogProps) {
  const t = useTranslations('settings.system.stackUpdate');
  if (fixed.length === 0 && other.length === 0) {
    return null;
  }

  const visibleFixed = expanded ? fixed : fixed.slice(0, 5);
  const visibleOther = expanded ? other : other.slice(0, 5);

  return (
    <div className="space-y-3">
      {fixed.length > 0 && (
        <div>
          <p className="text-xs font-bold text-foreground mb-1">{t('changelogFixed')}</p>
          <ul className="space-y-1">
            {visibleFixed.map((item, index) => (
              <li key={index} className="text-xs text-muted-foreground flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {other.length > 0 && (
        <div>
          <p className="text-xs font-bold text-foreground mb-1">{t('changelogOther')}</p>
          <ul className="space-y-1">
            {visibleOther.map((item, index) => (
              <li key={index} className="text-xs text-muted-foreground flex items-start gap-2">
                <span className="text-primary mt-0.5">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(fixed.length > 5 || other.length > 5) && (
        <button type="button" onClick={onToggleExpanded} className="text-xs font-bold text-primary hover:underline">
          {expanded ? t('showLess') : t('showMore')}
        </button>
      )}
    </div>
  );
}
