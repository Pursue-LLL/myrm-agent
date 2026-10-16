/**
 * [INPUT]
 * - @/lib/utils/imeUtils::installImeEnterGuard (POS: document 捕获阶段拦下输入法确认候选词的 Enter)
 *
 * [OUTPUT]
 * - ImeEnterGuardInitializer: 挂载期间安装输入法回车守卫，卸载时移除；不渲染任何内容
 *
 * [POS]
 * 根布局级副作用组件，与 ExternalLinkInitializer 同级 eager 挂载，覆盖所有路由（含不带应用壳的独立页），
 * 使中文 / 日文 / 韩文用户在任何输入框里按 Enter 选字上屏都不会触发提交、重命名或确认。
 */
'use client';

import { useEffect } from 'react';

import { installImeEnterGuard } from '@/lib/utils/imeUtils';

export default function ImeEnterGuardInitializer() {
  useEffect(() => installImeEnterGuard(), []);

  return null;
}
