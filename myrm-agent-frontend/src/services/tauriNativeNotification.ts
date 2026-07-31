/**
 * [INPUT]
 * - @tauri-apps/plugin-notification (POS: Tauri desktop native notification plugin)
 *
 * [OUTPUT]
 * - sendTauriNativeNotification: best-effort OS notification for hidden desktop window
 *
 * [POS]
 * Tauri-only notification helper shared by tray budget alerts and media task completion hooks.
 */

export async function sendTauriNativeNotification(options: {
  title: string;
  body?: string;
}): Promise<boolean> {
  try {
    const { sendNotification, isPermissionGranted, requestPermission } = await import(
      '@tauri-apps/plugin-notification'
    );
    let granted = await isPermissionGranted();
    if (!granted) {
      const permission = await requestPermission();
      granted = permission === 'granted';
    }
    if (!granted) {
      return false;
    }
    sendNotification({
      title: options.title,
      body: options.body,
    });
    return true;
  } catch {
    return false;
  }
}
