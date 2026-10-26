import { vi } from 'vitest';

/** Shared module doubles for the ima card tests; each test file wires them in with an async `vi.mock` factory. */
export const toastMock = { success: vi.fn(), error: vi.fn(), message: vi.fn() };

export const imaMock = {
  getImaStatus: vi.fn(),
  saveImaCredentials: vi.fn(),
  deleteImaCredentials: vi.fn(),
  listImaLibraries: vi.fn(),
  saveImaSelection: vi.fn(),
  startImaSync: vi.fn(),
  pauseImaSync: vi.fn(),
  resumeImaSync: vi.fn(),
  retryFailedImaItems: vi.fn(),
  compileImaImports: vi.fn(),
  listImaItems: vi.fn(),
};

export function resetImaMocks(): void {
  Object.values(imaMock).forEach((mock) => mock.mockReset());
  Object.values(toastMock).forEach((mock) => mock.mockReset());
  imaMock.listImaLibraries.mockResolvedValue([
    { id: 'kb1', name: 'Research' },
    { id: 'kb2', name: 'Recipes' },
  ]);
}
