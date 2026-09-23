/**
 * UTF-8 安全的 Base64 编解码工具。
 * 针对包含多字节 Unicode 字符（如中文、Emoji、数学符号等）的 Base64 字符串，
 * 使用标准 TextDecoder / TextEncoder 正确处理字节流，避免原生 atob 仅支持 Latin1 的致命乱码问题。
 */

/**
 * 安全解码包含多字节 UTF-8 的 Base64 字符串
 */
export function safeBase64DecodeUtf8(base64Str: string): string {
  if (!base64Str || typeof base64Str !== 'string') {
    return '';
  }

  const cleaned = base64Str.replace(/\s+/g, '');

  try {
    const binaryStr = atob(cleaned);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    return new TextDecoder('utf-8').decode(bytes);
  } catch {
    try {
      return decodeURIComponent(
        atob(cleaned)
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join(''),
      );
    } catch {
      return atob(cleaned);
    }
  }
}

/**
 * 将可能包含多字节 UTF-8 字符的字符串安全编码为 Base64
 */
export function safeBase64EncodeUtf8(str: string): string {
  if (!str || typeof str !== 'string') {
    return '';
  }

  try {
    const bytes = new TextEncoder().encode(str);
    let binary = '';
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  } catch {
    return btoa(
      encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, (_, p1: string) =>
        String.fromCharCode(parseInt(p1, 16)),
      ),
    );
  }
}
