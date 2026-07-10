type SubviewBackHandler = () => boolean;

let activeHandler: SubviewBackHandler | null = null;

export function registerSettingsSubviewBack(handler: SubviewBackHandler | null): void {
  activeHandler = handler;
}

export function trySettingsSubviewBack(): boolean {
  return activeHandler?.() ?? false;
}
