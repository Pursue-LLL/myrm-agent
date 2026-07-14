'use client';

/**
 * [INPUT]
 * @/store/useResearchStore (POS: Research 工作台全局状态)
 * @/services/wikiService (POS: Wiki API 客户端)
 * @/services/file (POS: 文件上传 API)
 *
 * [OUTPUT]
 * ResourcePoolPanel: 左栏资料池面板
 *
 * [POS]
 * Research 左栏资料池。支持 Wiki 概念搜索添加、文件上传和 checkbox 勾选。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Upload, CheckSquare, Square, Search, FileText, BookOpen, Trash2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { wikiService, type ConceptListResponse } from '@/services/wikiService';
import { uploadFiles } from '@/services/file';
import { resetUploadController, getUploadSignal } from '@/services/uploadController';
import useResearchStore, { type ResearchResource } from '@/store/useResearchStore';
import { cn } from '@/lib/utils/classnameUtils';

interface ResourceItemProps {
  resource: ResearchResource;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
}

function ResourceItem({ resource, onToggle, onRemove }: ResourceItemProps) {
  const Icon = resource.type === 'concept' ? BookOpen : FileText;

  return (
    <div
      className={cn(
        'group flex items-start gap-2 px-3 py-2 rounded-lg transition-colors cursor-pointer',
        'hover:bg-muted/50',
        resource.selected && 'bg-primary/5',
      )}
      onClick={() => onToggle(resource.id)}
    >
      <button
        className="mt-0.5 shrink-0 text-muted-foreground hover:text-primary transition-colors"
        aria-label={resource.selected ? 'Deselect' : 'Select'}
      >
        {resource.selected ? (
          <CheckSquare className="w-4 h-4 text-primary" />
        ) : (
          <Square className="w-4 h-4" />
        )}
      </button>

      <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{resource.name}</p>
        {resource.summary && (
          <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{resource.summary}</p>
        )}
      </div>

      <button
        className="shrink-0 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(resource.id);
        }}
        aria-label="Remove"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export default function ResourcePoolPanel() {
  const t = useTranslations('research');
  const {
    resources,
    addResource,
    removeResource,
    toggleResource,
    selectAll,
    deselectAll,
  } = useResearchStore();

  const [query, setQuery] = useState('');
  const [conceptResults, setConceptResults] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showConceptPicker, setShowConceptPicker] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedCount = resources.filter((r) => r.selected).length;
  const allSelected = resources.length > 0 && selectedCount === resources.length;

  const searchConcepts = useCallback(async (q: string) => {
    if (!q.trim()) {
      setConceptResults([]);
      return;
    }
    setIsSearching(true);
    try {
      const data: ConceptListResponse = await wikiService.listConcepts(q, 20, 0);
      setConceptResults(data.concepts);
    } catch {
      toast.error(t('errors.searchFailed'));
    } finally {
      setIsSearching(false);
    }
  }, [t]);

  useEffect(() => {
    if (!showConceptPicker) return;
    const timer = setTimeout(() => searchConcepts(query), 300);
    return () => clearTimeout(timer);
  }, [query, showConceptPicker, searchConcepts]);

  const handleAddConcept = useCallback(
    (conceptName: string) => {
      addResource({
        id: `concept:${conceptName}`,
        name: conceptName,
        type: 'concept',
      });
      toast.success(t('resourceAdded'));
    },
    [addResource, t],
  );

  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      setIsUploading(true);
      try {
        resetUploadController();
        const result = await uploadFiles(Array.from(files), getUploadSignal());
        if (result.uploaded_count > 0 && result.files) {
          for (const f of result.files) {
            addResource({
              id: `file:${f.fileUrl}`,
              name: f.fileName,
              type: 'raw_file',
            });
          }
          toast.success(t('filesUploaded', { count: result.uploaded_count }));
        }
      } catch {
        toast.error(t('errors.uploadFailed'));
      } finally {
        setIsUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
      }
    },
    [addResource, t],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('resourcePool')}</h3>
          <span className="text-xs text-muted-foreground">
            {t('selectedCount', { selected: selectedCount, total: resources.length })}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setShowConceptPicker(!showConceptPicker)}
              >
                <BookOpen className="w-3.5 h-3.5 mr-1" />
                {t('addFromWiki')}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('addFromWikiTooltip')}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
              >
                <Upload className="w-3.5 h-3.5 mr-1" />
                {isUploading ? t('uploading') : t('uploadFile')}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('uploadFileTooltip')}</TooltipContent>
          </Tooltip>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileUpload}
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt"
          />

          {resources.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs ml-auto"
              onClick={allSelected ? deselectAll : selectAll}
            >
              {allSelected ? t('deselectAll') : t('selectAll')}
            </Button>
          )}
        </div>
      </div>

      {/* Wiki Concept Picker */}
      {showConceptPicker && (
        <div className="px-4 py-2 border-b bg-muted/30 space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder={t('searchConcepts')}
              className="pl-8 h-8 text-xs"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <ScrollArea className="max-h-32">
            {isSearching ? (
              <p className="text-xs text-muted-foreground text-center py-2">{t('searching')}</p>
            ) : conceptResults.length > 0 ? (
              <div className="space-y-0.5">
                {conceptResults.map((name) => {
                  const alreadyAdded = resources.some((r) => r.id === `concept:${name}`);
                  return (
                    <button
                      key={name}
                      className={cn(
                        'w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted transition-colors',
                        alreadyAdded && 'opacity-50 cursor-default',
                      )}
                      onClick={() => !alreadyAdded && handleAddConcept(name)}
                      disabled={alreadyAdded}
                    >
                      <BookOpen className="w-3 h-3 inline mr-1.5" />
                      {name}
                      {alreadyAdded && <span className="ml-1 text-muted-foreground">({t('added')})</span>}
                    </button>
                  );
                })}
              </div>
            ) : query.trim() ? (
              <p className="text-xs text-muted-foreground text-center py-2">{t('noResults')}</p>
            ) : null}
          </ScrollArea>
        </div>
      )}

      {/* Resource List */}
      <ScrollArea className="flex-1">
        {resources.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-12 px-4 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <BookOpen className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">{t('emptyResources')}</p>
            <p className="text-xs text-muted-foreground mt-1">{t('emptyResourcesHint')}</p>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
            {resources.map((resource) => (
              <ResourceItem
                key={resource.id}
                resource={resource}
                onToggle={toggleResource}
                onRemove={removeResource}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
