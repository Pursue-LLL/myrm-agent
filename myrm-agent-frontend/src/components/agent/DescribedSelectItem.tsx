'use client';

/**
 * [INPUT] @/components/primitives/select::SelectItem (POS: Radix 下拉选项)
 * [OUTPUT] DescribedSelectItem: 带次级说明行的下拉选项（选中后触发器同样展示两行）
 * [POS] 智能体编辑表单中各类策略下拉共用的选项样式。
 */

import type { ReactNode } from 'react';
import { SelectItem } from '@/components/primitives/select';

interface DescribedSelectItemProps {
  value: string;
  label: ReactNode;
  description: ReactNode;
}

export function DescribedSelectItem({ value, label, description }: DescribedSelectItemProps) {
  return (
    <SelectItem value={value}>
      <div className="flex flex-col py-0.5">
        <span>{label}</span>
        <span className="text-xs text-muted-foreground">{description}</span>
      </div>
    </SelectItem>
  );
}
