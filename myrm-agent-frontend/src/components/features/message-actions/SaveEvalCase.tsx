import { Check, FlaskConical } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

const SaveEvalCase = ({ chatId }: { chatId: string }) => {
  const t = useTranslations('evalLab');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = useCallback(async () => {
    if (saving || saved) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/eval/cases/from-chat/${chatId}`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error('Failed to save eval case');
      }
      setSaved(true);
      toast.success(t('saveFromChatSuccess'));
      setTimeout(() => setSaved(false), 2000);
    } catch {
      toast.error(t('saveFromChatFailed'));
    } finally {
      setSaving(false);
    }
  }, [chatId, saving, saved, t]);

  const btnClass =
    'p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white';

  if (saved) {
    return (
      <span className={btnClass}>
        <Check size={18} className="text-green-500" />
      </span>
    );
  }

  return (
    <button
      onClick={handleSave}
      disabled={saving}
      className={`${btnClass} ${saving ? 'opacity-50 cursor-not-allowed' : ''}`}
      title={t('saveFromChatTitle')}
    >
      <FlaskConical size={18} className={saving ? 'animate-pulse text-primary' : ''} />
    </button>
  );
};

export default SaveEvalCase;
