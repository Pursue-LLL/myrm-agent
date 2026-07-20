'use client';

import { memo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Upload, File, Loader2, AlertCircle, CheckCircle2, DownloadCloud } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useDragDrop } from '@/hooks/useDragDrop';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/hooks/useToast';
import { resolveUserFacingArchiveSecurityError } from '@/services/archiveSecurityErrorCore';
interface SkillBatchImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

interface PreviewItem {
  virtual_id: string;
  name: string;
  description: string;
  conflict_type: 'none' | 'conflict';
  existing_skill_id: string | null;
  resolution: 'replace' | 'rename_cow' | 'skip' | 'new';
  security_issues?: string | null;
}

type PreviewResolution = PreviewItem['resolution'];

interface PreviewResponseItem {
  virtual_id: string;
  name: string;
  description: string;
  conflict_type: PreviewItem['conflict_type'];
  existing_skill_id: string | null;
  security_issues?: string | null;
}

interface ApiErrorPayload {
  detail?: unknown;
}

function parsePreviewResolution(value: string, fallback: PreviewResolution): PreviewResolution {
  if (value === 'replace' || value === 'rename_cow' || value === 'skip' || value === 'new') {
    return value;
  }
  return fallback;
}

function resolveErrorMessage(error: unknown, fallbackMessage: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallbackMessage;
}

const SkillBatchImportDialog = memo(({ open, onOpenChange, onImportComplete }: SkillBatchImportDialogProps) => {
  const t = useTranslations('settings.skills');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resolveUserFacingApiError = useCallback(
    (detail: unknown, fallbackMessage: string): string =>
      resolveUserFacingArchiveSecurityError(detail, fallbackMessage, (translationKey) =>
        t(translationKey as Parameters<typeof t>[0]),
      ),
    [t],
  );
  
  const [file, setFile] = useState<File | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [previewItems, setPreviewItems] = useState<PreviewItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [totalFound, setTotalFound] = useState(0);
  const [totalConflicts, setTotalConflicts] = useState(0);

  const resetForm = useCallback(() => {
    setFile(null);
    setParseError(null);
    setPreviewItems([]);
    setSessionId(null);
    setTotalFound(0);
    setTotalConflicts(0);
    setIsParsing(false);
    setIsImporting(false);
  }, []);

  const handleFilesSelected = useCallback(
    async (selectedFiles: FileList | File[]) => {
      const fileArray = Array.from(selectedFiles);
      if (fileArray.length !== 1) {
        setParseError(t('upload.singleArchiveOnly'));
        return;
      }
      const selected = fileArray[0];
      if (!selected.name.toLowerCase().endsWith('.zip')) {
        setParseError(t('upload.archiveOnly'));
        return;
      }
      if (selected.size > 10 * 1024 * 1024) {
        setParseError('文件大小不能超过 10MB，保护服务器内存。 / File size cannot exceed 10MB.');
        return;
      }
      setParseError(null);
      setFile(selected);
      
      // 自动触发预览
      setIsParsing(true);
      try {
        const formData = new FormData();
        formData.append('file', selected);
        
        const res = await fetch('/api/v1/skills/batch-import/preview', {
          method: 'POST',
          body: formData,
        });
        
        if (!res.ok) {
          const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
          const message = resolveUserFacingApiError(errPayload.detail, t('discover.previewFailed'));
          throw new Error(message);
        }
        
        const data = await res.json();
        setTotalFound(data.total_found);
        setTotalConflicts(data.total_conflicts);
        setSessionId(data.session_id);
        
        const items: PreviewItem[] = data.items.map((item: PreviewResponseItem) => ({
          ...item,
          resolution: item.conflict_type === 'conflict' ? 'rename_cow' : 'new'
        }));
        setPreviewItems(items);
        
      } catch (error: unknown) {
        setParseError(resolveErrorMessage(error, t('discover.previewFailed')));
        setFile(null);
      } finally {
        setIsParsing(false);
      }
    },
    [resolveUserFacingApiError, t],
  );

  const { isDragging, dragHandlers } = useDragDrop({
    onFilesSelected: handleFilesSelected,
    accept: ['application/zip'],
    maxFiles: 1,
    disabled: isParsing || isImporting,
  });

  const handleResolutionChange = (virtualId: string, resolution: PreviewResolution) => {
    setPreviewItems(prev => prev.map(item => 
      item.virtual_id === virtualId ? { ...item, resolution } : item
    ));
  };

  const handleBulkResolutionChange = useCallback((resolution: string) => {
    const parsedResolution = parsePreviewResolution(resolution, 'rename_cow');
    setPreviewItems(prev => prev.map(item => {
      if (item.conflict_type === 'conflict') {
        return { ...item, resolution: parsedResolution };
      }
      return item;
    }));
  }, []);

  const handleConfirmImport = async () => {
    try {
      setIsImporting(true);
      const payload = {
        session_id: sessionId,
        items: previewItems.map(item => ({
          virtual_id: item.virtual_id,
          name: item.name,
          description: item.description,
          resolution: item.resolution,
          existing_skill_id: item.existing_skill_id
        }))
      };
      
      const res = await fetch('/api/v1/skills/batch-import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        const message = resolveUserFacingApiError(errPayload.detail, t('installed.importFailed'));
        throw new Error(message);
      }
      
      const result = await res.json();
      toast({
        title: '导入成功 / Import Success',
        description: `成功导入 ${result.imported_count} 个技能，跳过 ${result.skipped_count} 个 / Imported ${result.imported_count}, skipped ${result.skipped_count}`,
      });
      resetForm();
      onOpenChange(false);
      onImportComplete();
      
    } catch (error: unknown) {
      toast({
        title: '导入失败 / Import Failed',
        description: resolveErrorMessage(error, t('installed.importFailed')),
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(val) => {
      if (!val) resetForm();
      onOpenChange(val);
    }}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-xl">
            <DownloadCloud className="w-5 h-5" />
            批量导入技能 / Batch Import Skills
          </DialogTitle>
          <DialogDescription>
            支持从 Hermes 协议或 ZIP 包无缝迁移。自动防爆、查杀恶意代码。 / Seamless migration from ZIP with anti-zip-bomb and AST scanner.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6 bg-muted/10">
          <div className="py-6 space-y-6">
            {!file ? (
              <div
                className={cn(
                  'border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors bg-background',
                  isDragging && 'border-primary bg-primary/5',
                  parseError && 'border-destructive bg-destructive/5',
                  !isDragging && !parseError && 'border-muted-foreground/25 hover:border-primary/50',
                )}
                {...dragHandlers}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.length) handleFilesSelected(e.target.files);
                  }}
                />
                {isParsing ? (
                  <Loader2 size={40} className="mx-auto mb-4 animate-spin text-primary" />
                ) : (
                  <Upload
                    size={40}
                    className={cn('mx-auto mb-4', parseError ? 'text-destructive' : 'text-muted-foreground')}
                  />
                )}
                
                <p className="text-base font-medium">
                  {isParsing ? '正在安全解压并分析... / Parsing & Scanning...' : '拖拽 ZIP 包到此处，或点击上传 / Drop ZIP here or click to upload'}
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  一次性导入数十个技能，告别繁琐。 / Import dozens of skills at once.
                </p>
                
                {parseError && (
                  <Alert variant="destructive" className="mt-6 text-left inline-block">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>解析失败 / Parse Error</AlertTitle>
                    <AlertDescription>{parseError}</AlertDescription>
                  </Alert>
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex items-center justify-between p-4 rounded-xl border bg-background">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <File className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <h4 className="font-medium">{file.name}</h4>
                      <p className="text-sm text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={resetForm} disabled={isImporting}>
                    重新上传 / Reselect
                  </Button>
                </div>
                
                <div className="space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <h3 className="font-medium text-base flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                        发现 {totalFound} 个技能 / Found {totalFound} Skills
                      </h3>
                      {totalConflicts > 0 && (
                        <Badge variant="outline" className="text-orange-500 border-orange-500/30 bg-orange-500/10">
                          {totalConflicts} 个重名冲突 / {totalConflicts} Conflicts
                        </Badge>
                      )}
                    </div>
                    {totalConflicts > 0 && (
                      <Select onValueChange={handleBulkResolutionChange} disabled={isImporting}>
                        <SelectTrigger className="w-[180px] h-8 text-xs bg-muted/50 border-dashed">
                          <SelectValue placeholder="一键处理所有冲突..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="rename_cow">全部重命名 (Rename All)</SelectItem>
                          <SelectItem value="replace">全部覆盖 (Replace All)</SelectItem>
                          <SelectItem value="skip">全部跳过 (Skip All)</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                  
                  <div className="border rounded-xl divide-y bg-background overflow-hidden">
                    {previewItems.map((item) => (
                      <div key={item.virtual_id} className="p-4 flex flex-col sm:flex-row gap-4 items-start sm:items-center hover:bg-muted/50 transition-colors">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium truncate">{item.name}</span>
                            {item.conflict_type === 'conflict' ? (
                              <Badge variant="destructive" className="text-[10px] px-1.5 py-0">冲突 / Conflict</Badge>
                            ) : (
                              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-green-500/10 text-green-600 dark:text-green-400">新增 / New</Badge>
                            )}
                            {item.security_issues && (
                              <Badge variant="destructive" className="text-[10px] px-1.5 py-0 bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20 flex items-center gap-1" title={item.security_issues}>
                                <AlertCircle className="w-3 h-3" /> 安全警告 / Security Risk
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-1">{item.description}</p>
                          {item.security_issues && (
                            <p className="text-[11px] text-destructive mt-1 line-clamp-1 flex items-center gap-1">
                              <AlertCircle className="w-3 h-3" /> {item.security_issues}
                            </p>
                          )}
                        </div>
                        
                        <div className="shrink-0 w-full sm:w-[180px]">
                          {item.conflict_type === 'conflict' ? (
                            <Select 
                              value={item.resolution} 
                              onValueChange={(value) =>
                                handleResolutionChange(item.virtual_id, parsePreviewResolution(value, item.resolution))
                              }
                              disabled={isImporting}
                            >
                              <SelectTrigger className="h-8 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="rename_cow">独立重命名 (CoW) / Rename</SelectItem>
                                <SelectItem value="replace">强制覆盖 / Replace</SelectItem>
                                <SelectItem value="skip">跳过 / Skip</SelectItem>
                              </SelectContent>
                            </Select>
                          ) : (
                            <Select 
                              value={item.resolution} 
                              onValueChange={(value) =>
                                handleResolutionChange(item.virtual_id, parsePreviewResolution(value, item.resolution))
                              }
                              disabled={isImporting}
                            >
                              <SelectTrigger className="h-8 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="new">正常导入 / Import</SelectItem>
                                <SelectItem value="skip">跳过 / Skip</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="p-6 pt-4 border-t flex items-center justify-between bg-background">
          <div className="text-sm text-muted-foreground">
            {previewItems.length > 0 && (
              <span>
                选定导入: {previewItems.filter(i => i.resolution !== 'skip').length} 个
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={isImporting}>
              取消 / Cancel
            </Button>
            <Button 
              onClick={handleConfirmImport} 
              disabled={!file || previewItems.length === 0 || isImporting || previewItems.every(i => i.resolution === 'skip')}
            >
              {isImporting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {isImporting ? '正在导入并查杀... / Importing...' : '确认导入 / Confirm Import'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});

SkillBatchImportDialog.displayName = 'SkillBatchImportDialog';

export default SkillBatchImportDialog;
