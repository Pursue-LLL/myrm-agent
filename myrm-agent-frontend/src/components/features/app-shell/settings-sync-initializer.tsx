'use client';

/**
 * 配置同步初始化组件
 *
 * 在应用顶层挂载：先同步应用已保存的聊天偏好，再启动配置同步（顺序见 `settings-sync-bootstrap`），
 * 并承载跨设备冲突的决策对话框：同步流程提出冲突，用户在对话框里选择保留本地或采用服务端。
 *
 * 支持的部署模式：
 * - Tauri 模式：同步到本地 SQLite
 * - Sandbox 模式：同步到云端数据库（敏感数据服务端加密）
 */

import { useEffect, useLayoutEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { ConfigConflictResolution } from '@/services/config/conflictResolution';
import { hydrateChatPreferencesFromStorage } from '@/store/useChatStore';
import ConfigConflictDialog from './ConfigConflictDialog';
import { bootstrapSettingsSync } from './settings-sync-bootstrap';

/** 正在询问用户的冲突，以及把决定交还给提问的同步流程的方式。 */
interface OpenQuestion {
  conflict: ConfigConflictResolution;
  decide: (keepLocal: boolean) => void;
}

export default function SettingsSyncInitializer() {
  const t = useTranslations('configConflict');
  const [question, setQuestion] = useState<OpenQuestion | null>(null);

  useLayoutEffect(() => {
    hydrateChatPreferencesFromStorage();
  }, []);

  useEffect(() => {
    // 一次只问一个：对话框打开期间到来的冲突排在当前问题之后，
    // 否则后来者会顶掉前一个问题，让等待它的同步流程永远等不到答案。
    let lastQuestion: Promise<unknown> = Promise.resolve();
    const ask = (conflict: ConfigConflictResolution) =>
      new Promise<boolean>((decide) => setQuestion({ conflict, decide }));

    void bootstrapSettingsSync((conflict) => {
      const decision = lastQuestion.then(() => ask(conflict));
      lastQuestion = decision;
      return decision;
    });
  }, []);

  const decide = (keepLocal: boolean) => {
    question?.decide(keepLocal);
    setQuestion(null);
  };

  return (
    <ConfigConflictDialog
      open={question !== null}
      conflict={question && { ...question.conflict, configLabel: t(`keys.${question.conflict.configKey}`) }}
      onKeepLocal={() => decide(true)}
      onUseServer={() => decide(false)}
      t={t}
    />
  );
}
