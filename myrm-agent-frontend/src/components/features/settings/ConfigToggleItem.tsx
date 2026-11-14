'use client';

import { useId } from 'react';
import { Switch } from '@/components/primitives/switch';

interface ConfigToggleItemProps {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

const ConfigToggleItem: React.FC<ConfigToggleItemProps> = ({
  icon: Icon,
  title,
  description,
  checked,
  onCheckedChange,
}) => {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <div className="flex items-center justify-between p-3 bg-secondary rounded-lg hover:bg-muted dark:hover:bg-muted transition-colors">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-muted rounded-lg">
          <Icon size={18} className="text-black/70 dark:text-white/70" />
        </div>
        <div>
          <p id={titleId} className="text-sm text-black/90 dark:text-white/90 font-medium">
            {title}
          </p>
          <p id={descriptionId} className="text-xs text-black/60 dark:text-white/60 mt-0.5">
            {description}
          </p>
        </div>
      </div>
      <Switch
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        checked={checked}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
};

export default ConfigToggleItem;
