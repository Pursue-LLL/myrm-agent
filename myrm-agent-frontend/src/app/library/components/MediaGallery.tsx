'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  Search,
  Image as ImageIcon,
  Loader2,
  X,
  Download,
  Tag,
  Maximize2,
  Trash2,
  CheckSquare,
  Square,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
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
import { useToast } from '@/hooks/useToast';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import {
  type MediaItem,
  type MediaQueryParams,
  fetchMediaList,
  fetchMediaTags,
  deleteMedia,
  updateMediaTags,
  batchDeleteMedia,
  batchUpdateTags,
  getMediaFileUrl,
  getMediaThumbnailUrl,
} from '@/services/media';

const TYPE_OPTIONS = ['image', 'video', 'audio'] as const;

export default function MediaGallery() {
  const t = useTranslations('library.gallery');
  const { toast } = useToast();
  const isMobile = useMediaQuery('(max-width: 768px)');

  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [mediaType, setMediaType] = useState<string>('');
  const [selectedTag, setSelectedTag] = useState<string>('');
  const [allTags, setAllTags] = useState<string[]>([]);

  const [lightboxItem, setLightboxItem] = useState<MediaItem | null>(null);
  const [editingTags, setEditingTags] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [pendingDelete, setPendingDelete] = useState<MediaItem | null>(null);

  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [batchTagInput, setBatchTagInput] = useState('');
  const [batchLoading, setBatchLoading] = useState(false);

  const observerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setKeyword(keywordInput), 300);
    return () => clearTimeout(timer);
  }, [keywordInput]);

  const fetchItems = useCallback(
    async (cursor?: string) => {
      const isLoadMore = !!cursor;
      if (isLoadMore) setLoadingMore(true);
      else setLoading(true);

      try {
        const params: MediaQueryParams = { limit: 24 };
        if (keyword) params.keyword = keyword;
        if (mediaType) params.media_type = mediaType;
        if (selectedTag) params.tags = selectedTag;
        if (cursor) params.cursor = cursor;

        const res = await fetchMediaList(params);
        setItems((prev) => (isLoadMore ? [...prev, ...res.items] : res.items));
        setNextCursor(res.next_cursor);
        setTotal(res.total);
      } catch {
        toast({ title: t('noResults'), variant: 'destructive' });
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [keyword, mediaType, selectedTag, toast, t],
  );

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  useEffect(() => {
    fetchMediaTags()
      .then(setAllTags)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!observerRef.current || !nextCursor) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && nextCursor && !loadingMore) {
          fetchItems(nextCursor);
        }
      },
      { threshold: 0.1 },
    );
    observer.observe(observerRef.current);
    return () => observer.disconnect();
  }, [nextCursor, loadingMore, fetchItems]);

  const requestDelete = (item: MediaItem) => setPendingDelete(item);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const item = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteMedia(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      setTotal((prev) => prev - 1);
      if (lightboxItem?.id === item.id) setLightboxItem(null);
      toast({ title: t('deleteSuccess') });
    } catch {
      toast({ title: t('deleteFailed'), variant: 'destructive' });
    }
  };

  const handleSaveTags = async () => {
    if (!lightboxItem) return;
    const newTags = tagInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const updated = await updateMediaTags(lightboxItem.id, newTags);
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      setLightboxItem(updated);
      setEditingTags(false);
      toast({ title: t('tagsUpdated') });
      fetchMediaTags()
        .then(setAllTags)
        .catch(() => {});
    } catch {
      toast({ title: t('tagsFailed'), variant: 'destructive' });
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(items.map((i) => i.id)));
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const confirmBatchDelete = async () => {
    const ids = [...selectedIds];
    setBatchDeleteOpen(false);
    setBatchLoading(true);
    try {
      const { deleted } = await batchDeleteMedia(ids);
      setItems((prev) => prev.filter((i) => !selectedIds.has(i.id)));
      setTotal((prev) => prev - deleted);
      toast({ title: t('batchDeleteSuccess', { count: deleted }) });
      exitSelectMode();
    } catch {
      toast({ title: t('deleteFailed'), variant: 'destructive' });
    } finally {
      setBatchLoading(false);
    }
  };

  const confirmBatchTag = async () => {
    const ids = [...selectedIds];
    const tags = batchTagInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    setBatchTagOpen(false);
    setBatchLoading(true);
    try {
      const { updated } = await batchUpdateTags(ids, tags);
      setItems((prev) => prev.map((i) => (selectedIds.has(i.id) ? { ...i, tags } : i)));
      toast({ title: t('batchTagSuccess', { count: updated }) });
      fetchMediaTags()
        .then(setAllTags)
        .catch(() => {});
      exitSelectMode();
    } catch {
      toast({ title: t('tagsFailed'), variant: 'destructive' });
    } finally {
      setBatchLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="pl-9"
          />
        </div>

        <select
          value={mediaType}
          onChange={(e) => setMediaType(e.target.value)}
          className="h-9 rounded-full border border-input bg-background px-3 text-sm"
        >
          <option value="">{t('allTypes')}</option>
          {TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {t(type === 'image' ? 'images' : type === 'video' ? 'videos' : 'audio')}
            </option>
          ))}
        </select>

        {allTags.length > 0 && (
          <select
            value={selectedTag}
            onChange={(e) => setSelectedTag(e.target.value)}
            className="h-9 rounded-full border border-input bg-background px-3 text-sm"
          >
            <option value="">{t('allTags')}</option>
            {allTags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        )}

        <span className="text-sm text-muted-foreground">
          {total} {t('images').toLowerCase()}
        </span>

        {items.length > 0 && (
          <Button
            variant={selectMode ? 'secondary' : 'outline'}
            size="sm"
            disabled={batchLoading}
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
          >
            {selectMode ? <X className="size-4 mr-1" /> : <CheckSquare className="size-4 mr-1" />}
            {selectMode ? t('cancel') : t('select')}
          </Button>
        )}
      </div>

      {selectMode && (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/50 border border-border">
          <Button variant="ghost" size="sm" onClick={toggleSelectAll} disabled={batchLoading}>
            {selectedIds.size === items.length ? t('deselectAll') : t('selectAll')}
          </Button>
          <span className="text-sm text-muted-foreground flex-1">{t('selected', { count: selectedIds.size })}</span>
          {batchLoading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          <Button
            variant="outline"
            size="sm"
            disabled={selectedIds.size === 0 || batchLoading}
            onClick={() => {
              setBatchTagInput('');
              setBatchTagOpen(true);
            }}
          >
            <Tag className="size-4 mr-1" />
            {t('batchTag')}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={selectedIds.size === 0 || batchLoading}
            onClick={() => setBatchDeleteOpen(true)}
          >
            <Trash2 className="size-4 mr-1" />
            {t('batchDelete')}
          </Button>
        </div>
      )}

      {/* Grid */}
      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <ImageIcon className="size-12 text-muted-foreground/40 mb-4" />
          <p className="text-lg font-medium text-foreground">{t('empty')}</p>
          <p className="text-sm text-muted-foreground mt-1">{t('emptyDesc')}</p>
        </div>
      ) : (
        <div
          className={cn(
            'grid gap-3',
            isMobile ? 'grid-cols-2' : 'grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6',
          )}
        >
          {items.map((item) => (
            <MediaCard
              key={item.id}
              item={item}
              selectMode={selectMode}
              selected={selectedIds.has(item.id)}
              onClick={() => {
                if (selectMode) {
                  toggleSelect(item.id);
                } else {
                  setLightboxItem(item);
                  setTagInput(item.tags.join(', '));
                  setEditingTags(false);
                }
              }}
              onDelete={() => requestDelete(item)}
            />
          ))}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      {nextCursor && (
        <div ref={observerRef} className="flex justify-center py-4">
          {loadingMore && <Loader2 className="size-5 animate-spin text-muted-foreground" />}
        </div>
      )}

      {/* Lightbox Dialog */}
      <Dialog open={!!lightboxItem} onOpenChange={(open) => !open && setLightboxItem(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="truncate text-sm">{lightboxItem?.prompt || lightboxItem?.id}</DialogTitle>
          </DialogHeader>

          {lightboxItem && (
            <div className="space-y-4">
              {/* Image */}
              <div className="relative flex justify-center bg-muted/30 rounded-lg overflow-hidden">
                <img
                  src={getMediaFileUrl(lightboxItem.id)}
                  alt={lightboxItem.prompt || ''}
                  className="max-h-[60vh] object-contain"
                />
              </div>

              {/* Metadata */}
              <div className="grid grid-cols-2 gap-2 text-sm">
                {lightboxItem.model && (
                  <div>
                    <span className="text-muted-foreground">{t('model')}: </span>
                    <span className="font-medium">{lightboxItem.model}</span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">{t('size')}: </span>
                  <span className="font-medium">{formatFileSize(lightboxItem.file_size)}</span>
                </div>
                {lightboxItem.resolution && (
                  <div>
                    <span className="text-muted-foreground">Resolution: </span>
                    <span className="font-medium">{lightboxItem.resolution}</span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">{t('createdAt')}: </span>
                  <span className="font-medium">{new Date(lightboxItem.created_at).toLocaleString()}</span>
                </div>
              </div>

              {/* Prompt */}
              {lightboxItem.prompt && (
                <div className="text-sm">
                  <span className="text-muted-foreground">{t('prompt')}: </span>
                  <span>{lightboxItem.prompt}</span>
                </div>
              )}

              {/* Tags */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Tag className="size-4 text-muted-foreground" />
                  {editingTags ? (
                    <div className="flex items-center gap-2 flex-1">
                      <Input
                        value={tagInput}
                        onChange={(e) => setTagInput(e.target.value)}
                        placeholder={t('addTag')}
                        className="h-8 text-sm"
                        onKeyDown={(e) => e.key === 'Enter' && handleSaveTags()}
                      />
                      <Button size="sm" variant="ghost" onClick={handleSaveTags}>
                        ✓
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingTags(false)}>
                        <X className="size-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1 flex-wrap">
                      {lightboxItem.tags.length > 0 ? (
                        lightboxItem.tags.map((tag) => (
                          <span key={tag} className="px-2 py-0.5 bg-muted rounded-full text-xs">
                            {tag}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-xs"
                        onClick={() => setEditingTags(true)}
                      >
                        {t('editTags')}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-2 border-t border-border">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(getMediaFileUrl(lightboxItem.id), '_blank')}
                >
                  <Maximize2 className="size-4 mr-1" />
                  {t('viewOriginal')}
                </Button>
                <a href={getMediaFileUrl(lightboxItem.id)} download className="inline-flex">
                  <Button variant="outline" size="sm">
                    <Download className="size-4 mr-1" />
                    {t('download')}
                  </Button>
                </a>
                <Button variant="destructive" size="sm" onClick={() => requestDelete(lightboxItem)}>
                  <Trash2 className="size-4 mr-1" />
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!pendingDelete} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirmDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>{t('confirm')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={batchDeleteOpen} onOpenChange={setBatchDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('batchDeleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('batchDeleteConfirmDesc', { count: selectedIds.size })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmBatchDelete}>{t('confirm')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={batchTagOpen} onOpenChange={setBatchTagOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('batchTag')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              value={batchTagInput}
              onChange={(e) => setBatchTagInput(e.target.value)}
              placeholder={t('batchTagPlaceholder')}
              onKeyDown={(e) => e.key === 'Enter' && confirmBatchTag()}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setBatchTagOpen(false)}>
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={confirmBatchTag}>
                {t('confirm')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MediaCard({
  item,
  selectMode,
  selected,
  onClick,
  onDelete,
}: {
  item: MediaItem;
  selectMode: boolean;
  selected: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  const thumbnailUrl = item.thumbnail_url ? getMediaThumbnailUrl(item.id) : getMediaFileUrl(item.id);

  return (
    <div
      className={cn(
        'group relative cursor-pointer rounded-lg overflow-hidden',
        'bg-muted/30 border-2 transition-all duration-200',
        'aspect-square',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border/50 hover:border-primary/30 hover:shadow-md',
      )}
      onClick={onClick}
    >
      <img src={thumbnailUrl} alt={item.prompt || ''} className="size-full object-cover" loading="lazy" />

      {selectMode && (
        <div className="absolute top-2 left-2 z-10">
          {selected ? (
            <CheckSquare className="size-5 text-primary drop-shadow-md" />
          ) : (
            <Square className="size-5 text-white/80 drop-shadow-md" />
          )}
        </div>
      )}

      <div
        className={cn(
          'absolute inset-0 transition-colors',
          selectMode ? (selected ? 'bg-primary/10' : 'bg-black/0') : 'bg-black/0 group-hover:bg-black/40',
        )}
      >
        {!selectMode && (
          <>
            <div className="absolute bottom-0 left-0 right-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <p className="text-xs text-white truncate">{item.prompt || item.model || item.id}</p>
            </div>
            <button
              className="absolute top-2 right-2 p-1 rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
            >
              <Trash2 className="size-3" />
            </button>
          </>
        )}
      </div>

      {!selectMode && item.tags.length > 0 && (
        <div className="absolute top-2 left-2">
          <div className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-black/40 text-white text-[10px]">
            <Tag className="size-2.5" />
            {item.tags.length}
          </div>
        </div>
      )}
    </div>
  );
}
