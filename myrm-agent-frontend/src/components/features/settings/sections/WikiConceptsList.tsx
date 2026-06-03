'use client';

/**
 * [INPUT] wiki/useWikiConceptsList, wiki/WikiConceptTree, wiki/WikiConceptDetailPanel
 * [OUTPUT] WikiConceptsList: Settings Wiki 词条管理页面
 * [POS] Settings → Wiki → 词条管理 Tab 编排层
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { IconBook, IconSearch } from '@/components/features/icons/PremiumIcons';
import { FolderPlus } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { useWikiConceptsList } from './wiki/useWikiConceptsList';
import { WikiConceptTree } from './wiki/WikiConceptTree';
import { WikiConceptDetailPanel } from './wiki/WikiConceptDetailPanel';
import { WikiFolderSelectTree } from './wiki/WikiFolderSelectTree';

export function WikiConceptsList() {
  const t = useTranslations('settings.wiki.concepts');
  const {
    query,
    setQuery,
    treeData,
    folderTreeData,
    isLoading,
    selectedConcept,
    isEditing,
    setIsEditing,
    editContent,
    setEditContent,
    isSaving,
    isDeleting,
    dialogOpen,
    setDialogOpen,
    dialogMode,
    dialogInput,
    setDialogInput,
    createParentFolder,
    setCreateParentFolder,
    deleteTarget,
    setDeleteTarget,
    treeRef,
    handleSelectConcept,
    handleMove,
    handleCreateFolder,
    handleRename,
    handleDeleteRequest,
    submitDialog,
    handleEdit,
    handleSave,
    confirmDelete,
  } = useWikiConceptsList();

  const treeContainerRef = useRef<HTMLDivElement>(null);
  const [treeHeight, setTreeHeight] = useState(400);

  useEffect(() => {
    const container = treeContainerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(([entry]) => {
      setTreeHeight(Math.max(entry.contentRect.height, 200));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const deleteDescription = deleteTarget
    ? deleteTarget.isDir
      ? t('deleteFolderConfirmDetail', { path: deleteTarget.name, count: deleteTarget.itemCount ?? 0 })
      : t('deleteConceptConfirmDetail', { path: deleteTarget.name })
    : '';

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1 min-h-[480px]">
      <Card className="col-span-1 flex flex-col h-full overflow-hidden min-h-0">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <IconBook className="w-4 h-4" />
              {t('title')}
            </CardTitle>
            <Button variant="ghost" size="icon" onClick={handleCreateFolder} title={t('createFolder')}>
              <FolderPlus className="w-4 h-4" />
            </Button>
          </div>
          <div className="relative mt-2">
            <IconSearch className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('searchPlaceholder')}
              className="pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto p-0 min-h-0">
          <div ref={treeContainerRef} className="h-full w-full min-h-[200px]">
            <WikiConceptTree
              treeRef={treeRef}
              treeData={treeData}
              query={query}
              treeHeight={treeHeight}
              isLoading={isLoading}
              selectedConcept={selectedConcept}
              isDeleting={isDeleting}
              onMove={handleMove}
              onSelectConcept={handleSelectConcept}
              onRename={handleRename}
              onDelete={handleDeleteRequest}
            />
          </div>
        </CardContent>
      </Card>

      <WikiConceptDetailPanel
        selectedConcept={selectedConcept}
        isEditing={isEditing}
        editContent={editContent}
        isSaving={isSaving}
        onEdit={handleEdit}
        onCancelEdit={() => setIsEditing(false)}
        onSave={handleSave}
        onEditContentChange={setEditContent}
      />

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>{dialogMode === 'create' ? t('createFolder') : t('rename')}</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            {dialogMode === 'create' && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">{t('parentFolderLabel')}</label>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setCreateParentFolder(null)}>
                    {t('parentFolderRoot')}
                  </Button>
                </div>
                <div className="border rounded-md h-[160px] overflow-auto p-2 bg-muted/20">
                  {folderTreeData.length === 0 ? (
                    <div className="text-center text-sm text-muted-foreground mt-8">{t('parentFolderRoot')}</div>
                  ) : (
                    <WikiFolderSelectTree
                      data={folderTreeData}
                      height={140}
                      selectedFolder={createParentFolder}
                      onSelectFolder={setCreateParentFolder}
                    />
                  )}
                </div>
                <p className="text-xs text-muted-foreground font-mono">{createParentFolder ?? t('parentFolderRoot')}</p>
              </div>
            )}
            <Input
              value={dialogInput}
              onChange={(e) => setDialogInput(e.target.value)}
              placeholder={t('namePlaceholder')}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submitDialog();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={() => void submitDialog()}>{t('confirm')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('delete')}</AlertDialogTitle>
            <AlertDialogDescription>{deleteDescription}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmDelete()}>{t('delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
