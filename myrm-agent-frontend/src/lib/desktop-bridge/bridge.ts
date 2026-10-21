/**
 * [INPUT]
 * - @/lib/tauri::isTauriEnvironment
 * - @/lib/desktop-bridge/types::IDesktopBridge
 * - @/lib/desktop-bridge/tauri-bridge::TauriDesktopBridge
 * - @/lib/desktop-bridge/web-fallback-bridge::WebFallbackDesktopBridge
 *
 * [OUTPUT]
 * - createDesktopBridge: Creates unified desktop bridge implementation based on environment
 * - defaultDesktopBridge / desktopBridge: Singleton instance of IDesktopBridge
 *
 * [POS]
 * Implementation of Standardized Desktop Bridge protocol. Provides runtime factory selection
 * and unified platform APIs across Web, Desktop, and Cloud. Platform detection lives in
 * platform-detection.ts (leaf module shared by factory and bridge implementations).
 */

import { isTauriEnvironment } from '@/lib/tauri';
import { TauriDesktopBridge } from './tauri-bridge';
import type { IDesktopBridge } from './types';
import { WebFallbackDesktopBridge } from './web-fallback-bridge';

export function createDesktopBridge(): IDesktopBridge {
  if (isTauriEnvironment()) {
    return new TauriDesktopBridge();
  }
  return new WebFallbackDesktopBridge();
}

export const defaultDesktopBridge: IDesktopBridge = createDesktopBridge();
export const desktopBridge: IDesktopBridge = defaultDesktopBridge;
