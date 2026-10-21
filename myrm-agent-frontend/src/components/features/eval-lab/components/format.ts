export function formatMib(bytes: number): string {
  if (bytes <= 0) {
    return '0 MB';
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
