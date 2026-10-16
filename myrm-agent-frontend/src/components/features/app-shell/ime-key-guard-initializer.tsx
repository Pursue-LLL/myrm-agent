/**
 * [INPUT]
 * - @/lib/utils/imeUtils::installImeKeyGuard (POS: window 捕获阶段拦下输入法确认候选词的 Enter 与取消组合的 Escape)
 *
 * [OUTPUT]
 * - ImeKeyGuardInitializer: 挂载期间安装输入法按键守卫，卸载时移除；不渲染任何内容
 *
 * [POS]
 * 根布局级副作用组件，与 ExternalLinkInitializer 同级 eager 挂载，覆盖所有路由（含不带应用壳的独立页），
 * 使中文 / 日文 / 韩文用户在任何输入框里按 Enter 选字上屏、按 Escape 取消拼音都不会触发提交、重命名、确认、
 * 关闭弹窗或中止运行中的任务。
 */
'use client';

import { useLayoutEffect } from 'react';

import { installImeKeyGuard } from '@/lib/utils/imeUtils';

export default function ImeKeyGuardInitializer() {
  // layout effect 先于整棵树的所有 passive effect 执行，守卫因此排在各功能 hook 的 window 捕获监听之前。
  useLayoutEffect(() => installImeKeyGuard(), []);

  return null;
}
