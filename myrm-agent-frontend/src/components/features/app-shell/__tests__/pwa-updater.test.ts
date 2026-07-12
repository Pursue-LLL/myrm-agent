import { describe, expect, it, vi } from 'vitest';

import { unregisterServiceWorkers } from '../pwa-updater';

describe('unregisterServiceWorkers', () => {
  it('unregisters every existing development registration', async () => {
    const firstUnregister = vi.fn().mockResolvedValue(true);
    const secondUnregister = vi.fn().mockResolvedValue(true);
    const container = {
      getRegistrations: vi.fn().mockResolvedValue([
        { unregister: firstUnregister },
        { unregister: secondUnregister },
      ]),
    } as unknown as ServiceWorkerContainer;

    await unregisterServiceWorkers(container);

    expect(container.getRegistrations).toHaveBeenCalledTimes(1);
    expect(firstUnregister).toHaveBeenCalledTimes(1);
    expect(secondUnregister).toHaveBeenCalledTimes(1);
  });

  it('handles an empty registration list', async () => {
    const container = {
      getRegistrations: vi.fn().mockResolvedValue([]),
    } as unknown as ServiceWorkerContainer;

    await expect(unregisterServiceWorkers(container)).resolves.toBeUndefined();
  });
});
