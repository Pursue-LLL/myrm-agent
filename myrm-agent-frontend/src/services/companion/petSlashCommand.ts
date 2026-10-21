/**
 * [INPUT]
 * - @/store/useFeatureGateStore (POS: 功能门控状态)
 * - @/store/useCompanionStore (POS: 伴侣全局状态)
 * - @/services/companion/petInstall::installCompanionPet (POS: Petdex install API 客户端)
 * - @/services/i18nToastService::showI18nToast (POS: i18n toast 封装)
 *
 * [OUTPUT]
 * - parsePetSlashArgs: 解析 /pet 参数字符串
 * - executePetSlashCommand: 执行 /pet slash（palette / toggle / slug install）
 *
 * [POS]
 * Companion /pet slash 命令执行层。供 builtinActions 与 useMessageInput submit 拦截复用。
 */

import { toast } from 'sonner';

import { installCompanionPet } from '@/services/companion/petInstall';
import { showI18nToast } from '@/services/i18nToastService';
import type { ActionResult } from '@/types/command';

export type PetSlashMode = 'palette' | 'toggle' | 'install';

export interface ParsedPetSlashArgs {
  mode: PetSlashMode;
  slug?: string;
}

export function parsePetSlashArgs(inputValue: string): ParsedPetSlashArgs {
  const args = inputValue.replace(/^\/pet\s*/i, '').trim();
  if (!args || args.toLowerCase() === 'list') {
    return { mode: 'palette' };
  }
  if (args.toLowerCase() === 'toggle') {
    return { mode: 'toggle' };
  }
  const slug = args.split(/\s+/)[0]?.trim();
  if (!slug) {
    return { mode: 'palette' };
  }
  return { mode: 'install', slug };
}

export async function executePetSlashCommand(inputValue: string): Promise<ActionResult> {
  const { useFeatureGateStore } = await import('@/store/useFeatureGateStore');
  if (!useFeatureGateStore.getState().isEnabled('companion_mode')) {
    showI18nToast('commands.builtin.petDisabled', undefined, { type: 'info' });
    return { success: false, error: 'Companion mode disabled' };
  }

  const { default: useCompanionStore } = await import('@/store/useCompanionStore');
  const store = useCompanionStore.getState();
  const parsed = parsePetSlashArgs(inputValue);

  if (parsed.mode === 'palette') {
    store.setPetPaletteOpen(true);
    return { success: true, newInputValue: '' };
  }

  if (parsed.mode === 'toggle') {
    if (!store.spriteConfig) {
      showI18nToast('commands.builtin.petNoActive', undefined, { type: 'info' });
      store.setPetPaletteOpen(true);
      return { success: true, newInputValue: '' };
    }
    const nextEnabled = !store.spriteEnabled;
    store.setSpriteEnabled(nextEnabled);
    await store.saveConfigToServer();
    if (nextEnabled) {
      showI18nToast('commands.builtin.petOverlayEnabled', undefined, { type: 'success' });
    } else {
      showI18nToast('commands.builtin.petOverlayDisabled', undefined, { type: 'info' });
    }
    return { success: true, newInputValue: '' };
  }

  const slug = parsed.slug;
  if (!slug) {
    return { success: false, error: 'Missing pet slug' };
  }

  const toastId = toast.loading('…');
  try {
    const installed = await installCompanionPet(slug);
    store.setSpriteConfig({
      petSlug: installed.slug,
      displayName: installed.display_name,
      contentSha256: installed.content_sha256,
    });
    store.setSpriteEnabled(true);
    await store.saveConfigToServer();
    toast.dismiss(toastId);
    showI18nToast('commands.builtin.petInstalled', { name: installed.display_name }, { type: 'success' });
    return { success: true, newInputValue: '' };
  } catch (e) {
    toast.dismiss(toastId);
    showI18nToast('commands.builtin.petInstallFailed', undefined, { type: 'error' });
    const msg = e instanceof Error ? e.message : 'Install failed';
    return { success: false, error: msg };
  }
}
