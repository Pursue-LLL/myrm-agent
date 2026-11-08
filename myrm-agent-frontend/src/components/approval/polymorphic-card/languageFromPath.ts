/** Monaco language id for a file path; unknown extensions are plain text and an empty path is markdown. */
export function getLanguageFromPath(filePath: string): string {
  if (!filePath) {
    return 'markdown';
  }
  const ext = filePath.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'py':
      return 'python';
    case 'json':
      return 'json';
    case 'html':
      return 'html';
    case 'css':
      return 'css';
    case 'md':
      return 'markdown';
    case 'sh':
    case 'bash':
      return 'shell';
    case 'yaml':
    case 'yml':
      return 'yaml';
    case 'rs':
      return 'rust';
    case 'go':
      return 'go';
    case 'java':
      return 'java';
    case 'cpp':
    case 'c':
    case 'h':
    case 'hpp':
      return 'cpp';
    default:
      return 'plaintext';
  }
}
