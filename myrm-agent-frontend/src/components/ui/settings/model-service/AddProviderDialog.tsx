'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CUSTOM_PROVIDER_TYPES, CUSTOM_PROVIDER_TYPE_INFO, CustomProviderType } from '@/store/config/providerTypes';

const ChevronDownIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="m6 9 6 6 6-6" />
  </svg>
);

interface AddProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (name: string, providerType: CustomProviderType) => void;
  existingIds: string[];
}

const AddProviderDialog = memo<AddProviderDialogProps>(({ open, onOpenChange, onAdd, existingIds }) => {
  const t = useTranslations('settings.modelService');
  const [name, setName] = useState('');
  const defaultProviderType = CUSTOM_PROVIDER_TYPES[0];
  const [providerType, setProviderType] = useState<CustomProviderType>(defaultProviderType);
  const [error, setError] = useState('');
  const [isTypeDropdownOpen, setIsTypeDropdownOpen] = useState(false);
  const providerTypeInfo = CUSTOM_PROVIDER_TYPE_INFO[providerType] ?? CUSTOM_PROVIDER_TYPE_INFO[defaultProviderType];

  const handleProviderTypeChange = (type: CustomProviderType) => {
    setProviderType(type);
    setIsTypeDropdownOpen(false);
  };

  const handleSubmit = () => {
    if (!name.trim()) {
      setError(t('providerNameRequired'));
      return;
    }

    const id = name.trim().toLowerCase().replace(/\s+/g, '_');
    if (existingIds.includes(id)) {
      setError(t('providerAlreadyExists'));
      return;
    }

    onAdd(name.trim(), providerType);
    handleClose();
  };

  const handleClose = () => {
    setName('');
    setProviderType(defaultProviderType);
    setError('');
    setIsTypeDropdownOpen(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('addCustomProvider')}</DialogTitle>
        </DialogHeader>

        <p className="text-xs text-muted-foreground leading-relaxed mt-2 px-0.5">{t('customProviderNotice')}</p>

        <div className="space-y-5 pt-4 pb-4">
          <div className="space-y-3">
            <label className="text-sm font-medium text-foreground block">
              {t('providerName')} <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              value={name || ''}
              onChange={(e) => {
                setName(e.target.value);
                setError('');
              }}
              placeholder={t('providerNamePlaceholder')}
              className="w-full px-3 py-2.5 text-sm bg-secondary/50 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <p className="text-xs text-muted-foreground">{t('providerNameHint')}</p>
          </div>

          {/* 提供商类型 */}
          <div className="space-y-3">
            <label className="text-sm font-medium text-foreground block">
              {t('providerType')} <span className="text-destructive">*</span>
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsTypeDropdownOpen(!isTypeDropdownOpen)}
                className="w-full px-3 py-2.5 text-sm bg-secondary/50 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 flex items-center justify-between"
              >
                <span>{providerTypeInfo.name}</span>
                <ChevronDownIcon
                  className={`w-4 h-4 text-muted-foreground transition-transform ${isTypeDropdownOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {isTypeDropdownOpen && (
                <div className="absolute z-10 w-full mt-1 bg-popover border border-border rounded-lg shadow-lg overflow-hidden">
                  {CUSTOM_PROVIDER_TYPES.map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => handleProviderTypeChange(type)}
                      className={`w-full px-3 py-2.5 text-sm text-left hover:bg-accent transition-colors ${
                        type === providerType ? 'bg-accent/50' : ''
                      }`}
                    >
                      {CUSTOM_PROVIDER_TYPE_INFO[type].name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{t('providerTypeHint')}</p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 text-sm font-medium text-foreground bg-secondary hover:bg-secondary/80 rounded-lg transition-colors"
          >
            {t('cancel')}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="px-4 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-lg transition-colors"
          >
            {t('add')}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
});

AddProviderDialog.displayName = 'AddProviderDialog';

export default AddProviderDialog;
