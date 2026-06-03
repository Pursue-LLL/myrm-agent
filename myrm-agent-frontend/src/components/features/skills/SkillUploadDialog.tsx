'use client';

import { memo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Upload, X, File, FileText, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useDragDrop } from '@/hooks/useDragDrop';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import { toast } from '@/hooks/useToast';
import { useSkillStore } from '@/store/skill';
import type { CreateCustomSkillRequest, Skill } from '@/store/skill/types';

// 预定义的分类（与后端一致）
const CATEGORIES = ['office', 'design', 'development', 'productivity', 'other'];

interface SkillUploadDialogProps {
  open: boolean;
  isUploading: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (request: CreateCustomSkillRequest) => Promise<Skill>;
}

interface ParsedSkillInfo {
  name: string;
  description: string;
}

const SkillUploadDialog = memo(({ open, isUploading, onOpenChange, onUpload }: SkillUploadDialogProps) => {
  const t = useTranslations('settings.skills');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isSandboxMode } = useSkillStore();

  // 表单状态
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<string>('other');
  const [tags, setTags] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);

  // 重置表单
  const resetForm = useCallback(() => {
    setFiles([]);
    setName('');
    setDescription('');
    setCategory('other');
    setTags('');
    setParseError(null);
  }, []);

  // 解析 SKILL.md 文件
  const _parseSkillMd = useCallback(async (file: File): Promise<ParsedSkillInfo | null> => {
    try {
      const content = await file.text();

      // 尝试解析 YAML frontmatter
      const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
      if (frontmatterMatch) {
        const frontmatter = frontmatterMatch[1];
        const nameMatch = frontmatter.match(/name:\s*(.+)/);
        const descMatch = frontmatter.match(/description:\s*(.+)/);

        return {
          name: nameMatch ? nameMatch[1].trim() : '',
          description: descMatch ? descMatch[1].trim() : '',
        };
      }

      // 如果没有 frontmatter，尝试从标题提取
      const titleMatch = content.match(/^#\s+(.+)/m);
      const firstParagraph = content.split('\n\n')[1] || '';

      return {
        name: titleMatch ? titleMatch[1].trim() : '',
        description: firstParagraph.trim().slice(0, 200),
      };
    } catch {
      return null;
    }
  }, []);

  // 检查文件是否为 zip 压缩包
  const isArchiveFile = useCallback((file: File): boolean => {
    const fileName = file.name.toLowerCase();
    return fileName.endsWith('.zip') || fileName.endsWith('.skill');
  }, []);

  // 处理文件选择
  const handleFilesSelected = useCallback(
    async (selectedFiles: FileList | File[]) => {
      const fileArray = Array.from(selectedFiles);

      // 只接受一个压缩包文件
      if (fileArray.length !== 1) {
        setParseError(t('upload.singleArchiveOnly'));
        return;
      }

      const file = fileArray[0];

      // 检查是否为压缩包
      if (!isArchiveFile(file)) {
        setParseError(t('upload.archiveOnly'));
        return;
      }

      setParseError(null);
      setFiles([file]);
    },
    [isArchiveFile, t],
  );

  // 拖拽上传（使用增强版 useDragDrop hook）
  const { isDragging, dragHandlers } = useDragDrop({
    onFilesSelected: handleFilesSelected,
    accept: ['application/zip', 'application/x-skill'],
    maxFiles: 1,
    disabled: isUploading,
  });

  // 点击选择文件
  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFilesSelected(e.target.files);
      }
    },
    [handleFilesSelected],
  );

  // 移除文件
  const handleRemoveFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // 提交上传
  const handleSubmit = useCallback(async () => {
    if (!name.trim()) {
      toast({
        title: t('upload.nameRequired'),
        variant: 'destructive',
      });
      return;
    }

    if (!description.trim()) {
      toast({
        title: t('upload.descriptionRequired'),
        variant: 'destructive',
      });
      return;
    }

    if (files.length === 0) {
      toast({
        title: t('upload.missingSkillMd'),
        variant: 'destructive',
      });
      return;
    }

    try {
      await onUpload({
        name: name.trim(),
        description: description.trim(),
        category: category || undefined,
        tags: tags.trim() || undefined,
        files,
      });

      toast({
        title: t('upload.success'),
        description: t('upload.successDesc', { name: name.trim() }),
      });

      resetForm();
      onOpenChange(false);
    } catch {
      toast({
        title: t('upload.failed'),
        variant: 'destructive',
      });
    }
  }, [name, description, files, category, tags, onUpload, onOpenChange, resetForm, t]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[85vh] flex flex-col p-0">
        <DialogHeader className="p-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            <Upload size={20} />
            {t('upload.title')}
          </DialogTitle>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6">
          <div className="py-4 space-y-6">
            {/* 文件拖拽区域 */}
            <div
              className={cn(
                'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
                isDragging && 'border-primary bg-primary/5',
                parseError && 'border-destructive',
                !isDragging && !parseError && 'border-muted-foreground/25 hover:border-primary/50',
              )}
              {...dragHandlers}
              onClick={handleClick}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,.skill"
                className="hidden"
                onChange={handleFileInputChange}
              />
              <Upload
                size={32}
                className={cn('mx-auto mb-3', parseError ? 'text-destructive' : 'text-muted-foreground')}
              />
              <p className="text-sm font-medium">{t('upload.dropzone')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('upload.dropzoneHint')}</p>
              {parseError && (
                <div className="flex items-center justify-center gap-1 mt-2 text-sm text-destructive">
                  <AlertCircle size={14} />
                  {parseError}
                </div>
              )}
            </div>

            {/* 网络限制提示 - 仅 Sandbox 模式 */}
            {isSandboxMode && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription className="text-sm">{t('upload.networkWarning')}</AlertDescription>
              </Alert>
            )}

            {/* 已选择的文件列表 */}
            {files.length > 0 && (
              <div className="space-y-2">
                <Label>{t('upload.files')}</Label>
                <div className="border rounded-lg divide-y">
                  {files.map((file, index) => (
                    <div key={`${file.name}-${index}`} className="flex items-center justify-between px-3 py-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {file.name.endsWith('.md') ? (
                          <FileText size={16} className="text-blue-500 flex-shrink-0" />
                        ) : (
                          <File size={16} className="text-muted-foreground flex-shrink-0" />
                        )}
                        <span className="text-sm truncate">{file.name}</span>
                        <span className="text-xs text-muted-foreground flex-shrink-0">
                          ({(file.size / 1024).toFixed(1)} KB)
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 flex-shrink-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveFile(index);
                        }}
                      >
                        <X size={14} />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 技能名称 */}
            <div className="space-y-3">
              <Label htmlFor="skill-name">
                {t('upload.name')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="skill-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('upload.namePlaceholder')}
                className="shadow-none focus-visible:ring-0"
              />
            </div>

            {/* 描述 */}
            <div className="space-y-3">
              <Label htmlFor="skill-description">
                {t('upload.description')} <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="skill-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('upload.descriptionPlaceholder')}
                rows={3}
                className="shadow-none focus-visible:ring-0"
              />
            </div>

            {/* 分类 */}
            <div className="space-y-3">
              <Label>{t('upload.category')}</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="shadow-none focus:ring-0">
                  <SelectValue placeholder={t('upload.categoryPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((cat) => (
                    <SelectItem key={cat} value={cat}>
                      {t(`categories.${cat}` as const)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* 标签 */}
            <div className="space-y-3">
              <Label htmlFor="skill-tags">{t('upload.tags')}</Label>
              <Input
                id="skill-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder={t('upload.tagsPlaceholder')}
                className="shadow-none focus-visible:ring-0"
              />
            </div>
          </div>
        </ScrollArea>

        {/* 底部操作 */}
        <div className="p-6 pt-4 border-t flex items-center justify-end gap-3">
          <Button
            variant="outline"
            onClick={() => {
              resetForm();
              onOpenChange(false);
            }}
          >
            {t('upload.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isUploading || files.length === 0 || !name.trim() || !description.trim()}
          >
            {isUploading && <Loader2 className="animate-spin mr-2" size={16} />}
            {isUploading ? t('upload.uploading') : t('upload.upload')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
});

SkillUploadDialog.displayName = 'SkillUploadDialog';

export default SkillUploadDialog;
