/**
 * Relative addresses in a workspace document.
 *
 * [INPUT]
 * - url: an image or link address as written in the document
 * - filePath / workspace: where the document is, and the workspace root the content API is bound to
 *
 * [OUTPUT]
 * - resolveWorkspaceUrl: the content URL of the file a relative address names; any other address as it was
 *
 * [POS]
 * Lets a markdown file in the workspace show the images beside it and link to its neighbours. Where the path ends
 * up is checked by the server against the workspace root, so a `../` that leaves it is refused there.
 */

import { getStorageUrl } from '@/lib/api';
import { getWorkspaceFileContentUrl } from '@/services/chat';

/** `https:`, `data:`, `mailto:` ...; `#section` and protocol-relative `//host` are no relative paths either. */
const NOT_RELATIVE = /^(?:[a-z][a-z0-9+.-]*:|#|\/)/i;

function decode(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

export function resolveWorkspaceUrl(url: string, filePath: string, workspace: string): string {
  if (url === '' || NOT_RELATIVE.test(url)) {
    return url;
  }
  const separator = filePath.includes('\\') && !filePath.includes('/') ? '\\' : '/';
  const resolved = filePath.split(/[\\/]/);
  resolved.pop();
  // The first segment is the root (empty for "/", the drive for "C:"); `..` never walks above it.
  const rootLength = 1;
  for (const part of decode(url.split(/[?#]/, 1)[0]).split(/[\\/]/)) {
    if (part === '..') {
      if (resolved.length > rootLength) {
        resolved.pop();
      }
    } else if (part !== '' && part !== '.') {
      resolved.push(part);
    }
  }
  return getStorageUrl(getWorkspaceFileContentUrl(resolved.join(separator), workspace));
}
