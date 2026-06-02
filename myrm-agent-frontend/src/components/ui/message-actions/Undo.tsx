import { Undo2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface UndoProps {
  onUndo: () => void;
}

const Undo = ({ onUndo }: UndoProps) => {
  const t = useTranslations('chat');

  return (
    <button
      onClick={onUndo}
      className="p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white"
      title={t('undo')}
    >
      <Undo2 size={18} />
    </button>
  );
};

export default Undo;
