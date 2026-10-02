/**
 * [INPUT]
 * - @/lib/desktop-bridge/types
 * - @/lib/desktop-bridge/bridge
 * - @/lib/desktop-bridge/tauri-bridge
 * - @/lib/desktop-bridge/web-fallback-bridge
 * - @/lib/desktop-bridge/platform-detection
 *
 * [OUTPUT]
 * - Re-exports types, classes, platform detection and singleton bridge instance
 *
 * [POS]
 * Desktop bridge module entrypoint.
 */

export * from './types';
export * from './bridge';
export * from './tauri-bridge';
export * from './web-fallback-bridge';
export * from './context';
export * from './platform-detection';
