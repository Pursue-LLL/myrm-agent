/**
 * Memory Command Center and in-UI experimental memory panels are opt-in.
 * Set NEXT_PUBLIC_MEMORY_LABS=1 (or legacy NEXT_PUBLIC_MEMORY_LAB=1) and restart WebUI.
 */
export function isMemoryLabsEnabled(): boolean {
  return (
    process.env.NEXT_PUBLIC_MEMORY_LABS === '1' || process.env.NEXT_PUBLIC_MEMORY_LAB === '1'
  );
}
