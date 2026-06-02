'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Search, X, Filter, ArrowUpDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import type { SkillFilters as SkillFiltersType, SkillSortBy, SkillSortOrder } from '@/store/skill/types';
import { SKILL_CATEGORIES } from './skillCategories';

const SORT_OPTIONS: { value: string; sortBy: SkillSortBy; order: SkillSortOrder }[] = [
  { value: 'name', sortBy: 'name', order: 'asc' },
  { value: 'created_at', sortBy: 'created_at', order: 'desc' },
];

interface SkillFiltersProps {
  filters: SkillFiltersType;
  availableTags: string[];
  onFiltersChange: (filters: Partial<SkillFiltersType>) => void;
  onClearFilters: () => void;
  onSortChange?: () => void; // 排序变更后触发重新获取数据
}

const SkillFilters = memo(
  ({ filters, availableTags, onFiltersChange, onClearFilters, onSortChange }: SkillFiltersProps) => {
    const t = useTranslations('settings.skills');

    const handleSearchChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onFiltersChange({ search: e.target.value });
      },
      [onFiltersChange],
    );

    const handleCategoryChange = useCallback(
      (value: string) => {
        onFiltersChange({ category: value === 'all' ? null : value });
      },
      [onFiltersChange],
    );

    const handleTagToggle = useCallback(
      (tag: string) => {
        const newTags = filters.tags.includes(tag) ? filters.tags.filter((t) => t !== tag) : [...filters.tags, tag];
        onFiltersChange({ tags: newTags });
      },
      [filters.tags, onFiltersChange],
    );

    const handleSortChange = useCallback(
      (value: string) => {
        const option = SORT_OPTIONS.find((opt) => opt.value === value);
        if (option) {
          onFiltersChange({ sortBy: option.sortBy, sortOrder: option.order });
          onSortChange?.();
        }
      },
      [onFiltersChange, onSortChange],
    );

    const currentSortValue = filters.sortBy;
    const hasActiveFilters = filters.search || filters.category || filters.tags.length > 0;

    return (
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        {/* 搜索框 */}
        <div className="relative flex-1 min-w-0">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder={t('filters.search')}
            value={filters.search}
            onChange={handleSearchChange}
            className="pl-9 pr-9"
          />
          {filters.search && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
              onClick={() => onFiltersChange({ search: '' })}
            >
              <X size={14} />
            </Button>
          )}
        </div>

        {/* 分类筛选 */}
        <Select value={filters.category || 'all'} onValueChange={handleCategoryChange}>
          <SelectTrigger className="w-full sm:w-[160px]">
            <SelectValue placeholder={t('filters.category')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('filters.categoryAll')}</SelectItem>
            {SKILL_CATEGORIES.map((category) => (
              <SelectItem key={category} value={category}>
                {t(`categories.${category}` as const)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 排序选择 */}
        <Select value={currentSortValue} onValueChange={handleSortChange}>
          <SelectTrigger className="w-full sm:w-[140px]">
            <ArrowUpDown size={14} className="mr-2 text-muted-foreground" />
            <SelectValue placeholder={t('filters.sort')} />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {t(`sort.${option.value}` as const)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 标签筛选 */}
        {availableTags.length > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="w-full sm:w-auto gap-2">
                <Filter size={16} />
                {t('filters.tags')}
                {filters.tags.length > 0 && (
                  <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">
                    {filters.tags.length}
                  </Badge>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-64" align="end">
              <div className="space-y-3">
                <p className="text-sm font-medium">{t('filters.tagsPlaceholder')}</p>
                <div className="max-h-[200px] overflow-y-auto space-y-2">
                  {availableTags.map((tag) => (
                    <label
                      key={tag}
                      className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 px-2 py-1 rounded"
                    >
                      <Checkbox checked={filters.tags.includes(tag)} onCheckedChange={() => handleTagToggle(tag)} />
                      <span className="text-sm">{tag}</span>
                    </label>
                  ))}
                </div>
              </div>
            </PopoverContent>
          </Popover>
        )}

        {/* 清除筛选 */}
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="text-muted-foreground hover:text-foreground"
          >
            <X size={14} className="mr-1" />
            {t('filters.clear')}
          </Button>
        )}
      </div>
    );
  },
);

SkillFilters.displayName = 'SkillFilters';

export default SkillFilters;
