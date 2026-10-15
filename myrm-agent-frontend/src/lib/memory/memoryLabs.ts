/**
 * Memory Command Center and in-UI experimental memory panels are opt-in.
 * Set NEXT_PUBLIC_MEMORY_LABS=1 and restart WebUI.
 */
export function isMemoryLabsEnabled(): boolean {
  return process.env.NEXT_PUBLIC_MEMORY_LABS === '1';
}
