import type { ElementType } from 'react';
import {
  BookOpenText,
  Code,
  Cpu,
  Database,
  FileSearch,
  GitBranch,
  LayoutGrid,
  LineChart,
  Palette,
  Play,
  Share2,
  Workflow,
  Zap,
} from 'lucide-react';
import type { SkillCategory } from '@/store/skill/types';

export const SKILL_CATEGORIES: readonly SkillCategory[] = [
  'development',
  'research',
  'creative',
  'productivity',
  'pipeline',
  'data',
  'data-science',
  'data-collection',
  'social-media',
  'media',
  'mlops',
  'workflow',
];

const CATEGORY_ICONS: Record<string, ElementType> = {
  development: Code,
  research: BookOpenText,
  creative: Palette,
  productivity: LayoutGrid,
  data: Database,
  'data-science': LineChart,
  'data-collection': FileSearch,
  'social-media': Share2,
  media: Play,
  pipeline: Workflow,
  mlops: Cpu,
  workflow: GitBranch,
  other: Zap,
};

const CATEGORY_COLORS: Record<string, string> = {
  development: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
  research: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  creative: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
  productivity: 'bg-green-500/10 text-green-600 dark:text-green-400',
  data: 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
  'data-science': 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
  'data-collection': 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
  'social-media': 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  media: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
  pipeline: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  mlops: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
  workflow: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
  other: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
};

export function getCategoryIcon(category: string | null | undefined): ElementType {
  return CATEGORY_ICONS[category || 'other'] || CATEGORY_ICONS.other;
}

export function getCategoryColor(category: string | null | undefined): string {
  return CATEGORY_COLORS[category || 'other'] || CATEGORY_COLORS.other;
}
