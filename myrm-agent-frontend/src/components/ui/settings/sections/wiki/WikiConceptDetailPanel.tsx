'use client';

import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { IconBook, IconEdit, IconLoader, IconSave, IconX } from '@/components/ui/icons/PremiumIcons';
import MarkdownContent from '@/components/ui/message-box/MarkdownContent';
import type { Concept } from '@/services/wikiService';

interface WikiConceptDetailPanelProps {
  selectedConcept: Concept | null;
  isEditing: boolean;
  editContent: string;
  isSaving: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onEditContentChange: (value: string) => void;
}

export function WikiConceptDetailPanel({
  selectedConcept,
  isEditing,
  editContent,
  isSaving,
  onEdit,
  onCancelEdit,
  onSave,
  onEditContentChange,
}: WikiConceptDetailPanelProps) {
  const t = useTranslations('settings.wiki.concepts');

  return (
    <Card className="col-span-1 md:col-span-2 h-full overflow-hidden flex flex-col min-h-0">
      {selectedConcept ? (
        <>
          <CardHeader className="border-b bg-muted/20 flex flex-row items-center justify-between py-4">
            <div className="font-semibold text-lg truncate pr-4">{selectedConcept.name}</div>
            <div className="flex gap-2 shrink-0">
              {isEditing ? (
                <>
                  <Button variant="outline" size="sm" onClick={onCancelEdit} disabled={isSaving}>
                    <IconX className="w-4 h-4 mr-2" />
                    {t('cancel')}
                  </Button>
                  <Button size="sm" onClick={() => void onSave()} disabled={isSaving}>
                    {isSaving ? (
                      <IconLoader className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <IconSave className="w-4 h-4 mr-2" />
                    )}
                    {t('save')}
                  </Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={onEdit}>
                  <IconEdit className="w-4 h-4 mr-2" />
                  {t('edit')}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto p-4 min-h-0">
            {isEditing ? (
              <textarea
                className="w-full h-full min-h-[280px] p-4 font-mono text-sm bg-background border rounded-md focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                value={editContent}
                onChange={(e) => onEditContentChange(e.target.value)}
                placeholder={t('editPlaceholder')}
              />
            ) : (
              <div className="prose dark:prose-invert max-w-none">
                <MarkdownContent
                  content={selectedConcept.content}
                  sources={[]}
                  messageId={`wiki-${selectedConcept.name}`}
                />
              </div>
            )}
          </CardContent>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4">
          <IconBook className="w-16 h-16 opacity-20" />
          <p>{t('selectToView')}</p>
        </div>
      )}
    </Card>
  );
}
