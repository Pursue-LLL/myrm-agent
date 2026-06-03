'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils/classnameUtils';
import { Artifact } from '@/store/chat/types';
import { Wand2, Download, Package, Loader2, Check } from 'lucide-react';
import { extractSkillDirectory } from '@/lib/constants/paths';
import { getFriendlyErrorMessage } from '@/lib/utils/skillErrorMapper';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/useToast';
import { packageWorkspaceDirectory, uploadSkill, triggerDownload } from '@/services/skill';
import { isLocalMode } from '@/lib/deploy-mode';
import { useSkillStore } from '@/store/skill';
import useAuthStore from '@/store/useAuthStore';
import useChatStore from '@/store/useChatStore';

// 默认空数组，避免每次创建新引用导致无限循环
const EMPTY_SKILL_IDS: string[] = [];

interface SkillDetectionCardProps {
  artifacts: Artifact[];
  chatId: string;
  className?: string;
}

/**
 * 技能检测卡片
 * 当工件列表中包含 SKILL.md 时显示，提供一键打包和注册功能
 */
const SkillDetectionCard: React.FC<SkillDetectionCardProps> = ({ artifacts, chatId, className }) => {
  const t = useTranslations('artifacts.skillActions');
  const [isPackaging, setIsPackaging] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isRegistered, setIsRegistered] = useState(false);

  const fetchMarketSkills = useSkillStore((state) => state.fetchMarketSkills);
  const marketSkills = useSkillStore((state) => state.marketSkills);
  const localSkills = useSkillStore((state) => state.localSkills);
  const user = useAuthStore((state) => state.user);

  // 获取当前聊天的技能配置
  // 使用 useShallow 避免因返回新引用导致无限重渲染
  const selectedSkillIds = useChatStore(useShallow((state) => state.agentConfig?.selectedSkillIds ?? EMPTY_SKILL_IDS));

  // 查找 SKILL.md 文件并获取其目录路径
  const skillMdArtifact = artifacts.find((artifact) => {
    const filename = artifact.filename.toLowerCase();
    // 检查文件名是 'skill.md' 或以 '/skill.md' 结尾
    return filename === 'skill.md' || filename.endsWith('/skill.md');
  });

  const hasSkillMd = !!skillMdArtifact;

  // 从 SKILL.md 路径提取技能目录
  // 使用统一的路径工具函数处理 files/ 前缀
  const skillDirectory = skillMdArtifact ? extractSkillDirectory(skillMdArtifact.filename) : '';

  // 标准化技能名称：移除 _skill 后缀并统一分隔符
  const normalizeSkillName = useCallback((name: string): string => {
    let normalized = name.toLowerCase().replace(/-/g, '_');
    // 移除 _skill 后缀
    if (normalized.endsWith('_skill')) {
      normalized = normalized.slice(0, -6);
    }
    return normalized;
  }, []);

  // 检查工件中的技能是否已经在用户的技能库中注册过
  const isSkillAlreadyRegistered = useMemo(() => {
    if (!skillDirectory) return false;

    // 检查是否是来自技能存储的路径（预构建或本地技能）
    // 格式: skills/prebuilt/xxx, skills/xxx
    // 或 Claude 标准路径: .claude/skills/xxx
    const isFromSkillStorage = skillDirectory.startsWith('skills/') || skillDirectory.startsWith('.claude/skills/');

    // 如果是来自技能存储的路径，说明这是已有技能，已经注册过
    if (isFromSkillStorage) {
      return true;
    }

    const allSkills = [...marketSkills, ...localSkills];
    const directoryParts = skillDirectory.split('/');
    const extractedName = directoryParts[directoryParts.length - 1];
    const normalizedDirectory = normalizeSkillName(extractedName);

    const matchingSkill = allSkills.find((skill) => {
      const normalized = normalizeSkillName(skill.name);
      return normalized === normalizedDirectory;
    });

    return !!matchingSkill;
  }, [skillDirectory, marketSkills, localSkills, normalizeSkillName]);

  const isSkillAlreadyInUse = useMemo(() => {
    if (!skillDirectory || selectedSkillIds.length === 0) return false;

    const allSkills = [...marketSkills, ...localSkills];
    const directoryParts = skillDirectory.split('/');
    const extractedName = directoryParts[directoryParts.length - 1];
    const normalizedDirectory = normalizeSkillName(extractedName);

    const matchingSkill = allSkills.find((skill) => {
      const normalized = normalizeSkillName(skill.name);
      return normalized === normalizedDirectory;
    });

    if (matchingSkill) {
      return selectedSkillIds.includes(matchingSkill.id);
    }

    return false;
  }, [skillDirectory, selectedSkillIds, marketSkills, localSkills, normalizeSkillName]);

  // 打包下载工作区
  const handlePackageDownload = useCallback(async () => {
    if (!chatId) return;

    setIsPackaging(true);
    try {
      // 传递技能目录路径，而不是空字符串
      const blob = await packageWorkspaceDirectory(chatId, skillDirectory);
      // 使用目录名作为 ZIP 文件名
      const zipName = skillDirectory || 'skill_package';
      triggerDownload(blob, `${zipName}.zip`);

      toast({
        title: t('packageSuccess'),
      });
    } catch (error) {
      console.error('Package failed:', error);
      const errorMessage = error instanceof Error ? error.message : '';
      toast({
        title: t('packageFailed'),
        description: getFriendlyErrorMessage(errorMessage, t),
        variant: 'destructive',
      });
    } finally {
      setIsPackaging(false);
    }
  }, [chatId, skillDirectory, t]);

  // 打包并注册技能
  const handlePackageAndRegister = useCallback(async () => {
    if (!chatId) return;

    setIsRegistering(true);
    try {
      // 1. 先打包工作区（传递正确的目录路径）
      const blob = await packageWorkspaceDirectory(chatId, skillDirectory);

      // 2. 转换为 File 对象（使用目录名作为 ZIP 文件名）
      const zipName = skillDirectory || 'skill';
      const zipFile = new File([blob], `${zipName}.zip`, { type: 'application/zip' });

      // 3. 上传并注册
      const result = await uploadSkill(zipFile, true);

      if (result.success) {
        // 标记为已注册
        setIsRegistered(true);

        if (user?.id) {
          await fetchMarketSkills(true);
        }

        toast({
          title: t('registerSuccess'),
          description: result.skill_name || undefined,
        });
      } else {
        toast({
          title: t('registerFailed'),
          description: result.error ? getFriendlyErrorMessage(result.error, t) : undefined,
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Register failed:', error);
      const errorMessage = error instanceof Error ? error.message : '';
      toast({
        title: t('registerFailed'),
        description: getFriendlyErrorMessage(errorMessage, t),
        variant: 'destructive',
      });
    } finally {
      setIsRegistering(false);
    }
  }, [chatId, skillDirectory, t, user?.id, fetchMarketSkills]);

  // 如果没有 SKILL.md，不显示
  // 如果技能已被用户在当前会话中选择使用，也不显示（避免重复提示）
  // 如果技能已经注册过，也不显示（避免重复注册）
  if (!hasSkillMd || isSkillAlreadyInUse || isSkillAlreadyRegistered) {
    return null;
  }

  const isLoading = isPackaging || isRegistering;

  return (
    <div
      className={cn(
        'flex flex-col p-4 rounded-lg border bg-gradient-to-r from-primary/5 to-primary/10 border-primary/20',
        className,
      )}
    >
      {/* 标题 */}
      <div className="flex items-center gap-2 mb-2">
        <Wand2 className="w-5 h-5 text-primary" />
        <h4 className="text-sm font-medium text-foreground">{t('skillDetected')}</h4>
      </div>

      {/* 描述 */}
      <p className="text-xs text-muted-foreground mb-3">{t('skillDetectedDesc')}</p>

      {/* 操作按钮 */}
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="flex-1" onClick={handlePackageDownload} disabled={isLoading}>
          {isPackaging ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Download className="w-4 h-4 mr-1" />}
          {isPackaging ? t('packaging') : t('packageAndDownload')}
        </Button>

        {!isLocalMode() && (
          <Button
            variant={isRegistered ? 'outline' : 'default'}
            size="sm"
            className={cn('flex-1', isRegistered && 'border-green-500 text-green-600')}
            onClick={handlePackageAndRegister}
            disabled={isLoading || isRegistered}
          >
            {isRegistering ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : isRegistered ? (
              <Check className="w-4 h-4 mr-1" />
            ) : (
              <Package className="w-4 h-4 mr-1" />
            )}
            {isRegistering ? t('registering') : isRegistered ? t('registered') : t('packageAndRegister')}
          </Button>
        )}
      </div>
    </div>
  );
};

export default SkillDetectionCard;
