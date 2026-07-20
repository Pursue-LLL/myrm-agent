import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { parseIntentUrl, UIPIntent } from './schema';
import { toast } from 'sonner';

/**
 * [POS] Universal Intent Protocol (UIP) Dispatcher.
 * Executes the validated intent by interacting with the Next.js router or global state.
 * Supports both raw URL parsing and page-provided parsed intents.
 */

export class IntentDispatcher {
  private router: AppRouterInstance;
  private openFlowPad: (text: string) => void;

  constructor(router: AppRouterInstance, openFlowPad: (text: string) => void) {
    this.router = router;
    this.openFlowPad = openFlowPad;
  }

  public async dispatch(rawUrl: string, parsedIntent?: UIPIntent): Promise<boolean> {
    try {
      console.log(`[UIP] Received deep link: ${rawUrl}`);
      const intent = parsedIntent ?? parseIntentUrl(rawUrl);
      await this.execute(intent);
      return true;
    } catch (error) {
      console.error('[UIP] Dispatch failed:', error);
      toast.error('无效的外部链接或参数错误');
      return false;
    }
  }

  private async execute(intent: UIPIntent) {
    console.log(`[UIP] Executing intent:`, intent);

    // Ensure the window is visible and focused when receiving a deep link
    if (typeof window !== 'undefined' && window.__TAURI_INTERNALS__) {
      try {
        // Dynamic import keeps browser/desktop APIs out of SSR evaluation.
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const appWindow = getCurrentWindow();
        // Ensure tray-hidden windows can be restored before focusing.
        await appWindow.show();
        await appWindow.unminimize();
        await appWindow.setFocus();
      } catch (e) {
        console.error('[UIP] Failed to focus window:', e);
      }
    }

    switch (intent.action) {
      case 'chat':
        this.router.push(`/chat/${intent.id}`);
        break;
      case 'agent':
        this.router.push(`/agents/${intent.id}`);
        break;
      case 'ask':
        this.openFlowPad(intent.text);
        break;
      case 'oauth':
        // Handle OAuth callback (e.g., save token, redirect to settings)
        // For now, just show a toast and redirect to settings
        toast.success('授权成功');
        this.router.push('/settings');
        break;
      case 'install-skill':
        this.router.push(`/settings/skills?action=install&url=${encodeURIComponent(intent.url)}`);
        break;
    }
  }
}
