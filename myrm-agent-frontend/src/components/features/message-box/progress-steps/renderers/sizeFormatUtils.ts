export function formatStoredSize(chars: number): string {
  if (chars < 1024) {
    return `${chars} B`;
  }
  if (chars < 1024 * 1024) {
    return `${(chars / 1024).toFixed(1)} KB`;
  }
  return `${(chars / (1024 * 1024)).toFixed(1)} MB`;
}
