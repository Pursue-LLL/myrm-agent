import { Switch } from '@/components/ui/switch';

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
  return (
    <div className="flex items-center justify-between p-3 bg-secondary rounded-lg hover:bg-muted dark:hover:bg-muted transition-colors">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-muted rounded-lg">
          <Icon size={18} className="text-black/70 dark:text-white/70" />
        </div>
        <div>
          <p className="text-sm text-black/90 dark:text-white/90 font-medium">{title}</p>
          <p className="text-xs text-black/60 dark:text-white/60 mt-0.5">{description}</p>
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
};

export default ConfigToggleItem;
