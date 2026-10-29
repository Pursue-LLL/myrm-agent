"""Visitor-side decryptor page for password-protected static publishes.

[INPUT]
- dict[str, str]: the AES-256-GCM payload fields (salt, nonce, ciphertext, iterations) embedded in the page
- str: the page title shown in the browser tab

[OUTPUT]
- render_decryptor_shell: one self-contained HTML document that asks the visitor for the password, decrypts the embedded
  bundle with the browser's Web Crypto API and mounts it in a sandboxed iframe

[POS]
The page every visitor of an encrypted publish opens: a lock card plus the in-browser decrypt-and-mount script, with the
ciphertext embedded by ``crypto_packager``.
"""

from __future__ import annotations

import html
import json


def render_decryptor_shell(encrypted_data: dict[str, str], title: str = "Protected Artifact") -> str:
    """Generate standalone HTML decryptor shell using browser-native Web Crypto API."""
    data_json = json.dumps(encrypted_data)
    safe_title = html.escape(title)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: radial-gradient(circle at 50% 0%, #1e1e2d 0%, #0d0d12 100%);
      color: #f3f4f6;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }}
    .card {{
      background: #20202b;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 1.25rem;
      padding: 2.25rem;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      text-align: center;
    }}
    .icon {{
      width: 48px;
      height: 48px;
      margin: 0 auto 1.25rem;
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.1);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; color: #fff; }}
    p {{ font-size: 0.875rem; color: #9ca3af; margin-bottom: 1.5rem; }}
    .input-group {{ margin-bottom: 1.25rem; text-align: left; }}
    input[type="password"] {{
      width: 100%;
      padding: 0.75rem 1rem;
      background: #17171e;
      border: 1px solid #6b7280;
      border-radius: 0.75rem;
      color: #fff;
      font-size: 0.95rem;
      outline: none;
      transition: all 0.2s;
    }}
    input[type="password"]::placeholder {{ color: #9ca3af; opacity: 1; }}
    input[type="password"]:focus {{
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
      outline: 2px solid transparent;
    }}
    button {{
      width: 100%;
      padding: 0.75rem 1rem;
      background: #0369a1;
      color: #fff;
      border: none;
      border-radius: 0.75rem;
      font-size: 0.95rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
    }}
    button:hover {{ background: #075985; }}
    button:active {{ transform: scale(0.99); }}
    button:disabled {{ background: #374151; cursor: not-allowed; }}
    .error {{
      margin-top: 1rem;
      font-size: 0.825rem;
      color: #f87171;
      display: none;
    }}
    .notice {{
      text-align: left;
      line-height: 1.4;
      color: #fbbf24;
      background: #36302a;
      border: 1px solid rgba(251, 191, 36, 0.3);
      padding: 0.75rem;
      border-radius: 0.5rem;
    }}
    body.unlocked {{ background: #fff; }}
    .fatal {{ margin: 0; padding: 2rem; font-size: 1rem; color: #b91c1c; }}
    #app-container {{
      display: none;
      width: 100vw;
      height: 100vh;
      position: fixed;
      top: 0;
      left: 0;
      border: none;
      background: #fff;
    }}

    /* 系统偏好减少动态效果时把过渡收到瞬时：解锁页是独立文档，宿主样式表的守卫到不了这里。 */
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }}
    }}
  </style>
</head>
<body>
  <div class="card" id="lock-card">
    <div class="icon">
      <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
        <path d="M7 11V7a5 5 0 0110 0v4"></path>
      </svg>
    </div>
    <h1>Protected Content</h1>
    <p>This artifact is password protected. Enter password to view.</p>
    <form id="decrypt-form" onsubmit="event.preventDefault(); handleUnlock();">
      <div class="input-group">
        <input type="password" id="pass-input" placeholder="Enter password..." autocomplete="current-password" autofocus required />
      </div>
      <button type="submit" id="unlock-btn">Unlock & View</button>
      <div class="error" id="error-msg" role="alert">Incorrect password. Please check it and try again.</div>
      <div class="error notice" id="env-error-msg" role="alert"></div>
    </form>
  </div>
  <iframe id="app-container" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"></iframe>

  <script>
    const encryptedData = {data_json};

    function checkSecureContext() {{
      const hasSubtle = typeof window !== "undefined" && window.crypto && window.crypto.subtle;
      if (!hasSubtle) {{
        const envErr = document.getElementById("env-error-msg");
        const btn = document.getElementById("unlock-btn");
        const passInput = document.getElementById("pass-input");
        if (envErr) {{
          envErr.style.display = "block";
          envErr.textContent = "This page can only be unlocked over a secure connection. Open the link that starts with https://, or save this page and open it from your computer.";
        }}
        if (btn) btn.disabled = true;
        if (passInput) passInput.disabled = true;
        return false;
      }}
      return true;
    }}

    document.addEventListener("DOMContentLoaded", checkSecureContext);
    if (document.readyState === "interactive" || document.readyState === "complete") {{
      checkSecureContext();
    }}

    function b64ToBuf(b64) {{
      const bin = atob(b64);
      const buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      return buf;
    }}

    async function deriveKey(password, salt, iterations) {{
      const enc = new TextEncoder();
      const baseKey = await crypto.subtle.importKey(
        "raw",
        enc.encode(password),
        "PBKDF2",
        false,
        ["deriveKey"]
      );
      return crypto.subtle.deriveKey(
        {{
          name: "PBKDF2",
          salt: salt,
          iterations: iterations,
          hash: "SHA-256",
        }},
        baseKey,
        {{ name: "AES-GCM", length: 256 }},
        false,
        ["decrypt"]
      );
    }}

    async function handleUnlock() {{
      const input = document.getElementById("pass-input");
      const btn = document.getElementById("unlock-btn");
      const error = document.getElementById("error-msg");
      const password = input.value.trim();
      if (!password) return;

      if (!checkSecureContext()) return;

      btn.disabled = true;
      btn.textContent = "Unlocking...";
      error.style.display = "none";

      try {{
        const salt = b64ToBuf(encryptedData.salt);
        const nonce = b64ToBuf(encryptedData.nonce);
        const ciphertext = b64ToBuf(encryptedData.ciphertext);
        const iterations = parseInt(encryptedData.iterations, 10);

        const key = await deriveKey(password, salt, iterations);
        const decrypted = await crypto.subtle.decrypt(
          {{ name: "AES-GCM", iv: nonce }},
          key,
          ciphertext
        );

        const dec = new TextDecoder();
        const vfs = JSON.parse(dec.decode(decrypted));

        renderVfs(vfs);
      }} catch (err) {{
        console.error("Decryption failed:", err);
        error.style.display = "block";
        btn.disabled = false;
        btn.textContent = "Unlock & View";
      }}
    }}

    function renderVfs(vfs) {{
      document.getElementById("lock-card").style.display = "none";
      document.body.classList.add("unlocked");
      const iframe = document.getElementById("app-container");
      iframe.style.display = "block";

      const entryFile = vfs["index.html"] || vfs[Object.keys(vfs).find(k => k.endsWith(".html"))];
      if (!entryFile) {{
        document.body.innerHTML = "<p class='fatal'>This page has no content to show.</p>";
        return;
      }}

      let htmlContent = entryFile.encoding === "base64"
        ? new TextDecoder().decode(b64ToBuf(entryFile.content))
        : entryFile.content;

      function getMimeType(path) {{
        if (path.endsWith(".css")) return "text/css";
        if (path.endsWith(".js") || path.endsWith(".mjs")) return "application/javascript";
        if (path.endsWith(".json")) return "application/json";
        if (path.endsWith(".svg")) return "image/svg+xml";
        if (path.endsWith(".png")) return "image/png";
        if (path.endsWith(".jpg") || path.endsWith(".jpeg")) return "image/jpeg";
        if (path.endsWith(".webp")) return "image/webp";
        if (path.endsWith(".gif")) return "image/gif";
        if (path.endsWith(".woff2")) return "font/woff2";
        if (path.endsWith(".woff")) return "font/woff";
        if (path.endsWith(".ttf")) return "font/ttf";
        if (path.endsWith(".mp3")) return "audio/mpeg";
        if (path.endsWith(".mp4")) return "video/mp4";
        return "application/octet-stream";
      }}

      function createAssetBlob(file, path) {{
        const mime = getMimeType(path);
        if (file.encoding === "base64") {{
          return new Blob([b64ToBuf(file.content)], {{ type: mime }});
        }}
        return new Blob([file.content], {{ type: mime }});
      }}

      // Step 1: Create Blob URLs for all leaf/media/font assets first (non-HTML, non-CSS, non-JS)
      const leafBlobMap = {{}};
      const cssPaths = [];
      const jsPaths = [];
      const allAssetKeys = Object.keys(vfs)
        .filter(k => k !== "index.html" && !k.endsWith(".html"))
        .sort((a, b) => b.length - a.length);

      for (const path of allAssetKeys) {{
        if (path.endsWith(".css")) {{
          cssPaths.push(path);
        }} else if (path.endsWith(".js") || path.endsWith(".mjs")) {{
          jsPaths.push(path);
        }} else {{
          leafBlobMap[path] = URL.createObjectURL(createAssetBlob(vfs[path], path));
        }}
      }}

      // Step 2: For CSS files, substitute leaf asset Blob URLs before creating CSS Blob URLs
      const cssBlobMap = {{}};
      for (const path of cssPaths) {{
        let cssText = vfs[path].encoding === "base64"
          ? new TextDecoder().decode(b64ToBuf(vfs[path].content))
          : vfs[path].content;
        for (const leafPath of Object.keys(leafBlobMap).sort((a, b) => b.length - a.length)) {{
          const leafUrl = leafBlobMap[leafPath];
          cssText = cssText.split("./" + leafPath).join(leafUrl);
          cssText = cssText.split("/" + leafPath).join(leafUrl);
          cssText = cssText.split(leafPath).join(leafUrl);
        }}
        const cssBlob = new Blob([cssText], {{ type: "text/css" }});
        cssBlobMap[path] = URL.createObjectURL(cssBlob);
      }}

      // Step 3: For JS files, create their Blob URLs
      const jsBlobMap = {{}};
      for (const path of jsPaths) {{
        jsBlobMap[path] = URL.createObjectURL(createAssetBlob(vfs[path], path));
      }}

      // Step 4: Replace all resolved asset URLs in htmlContent (sorted by descending length)
      const allResolvedBlobs = Object.assign({{}}, leafBlobMap, cssBlobMap, jsBlobMap);
      const sortedResolvedKeys = Object.keys(allResolvedBlobs).sort((a, b) => b.length - a.length);
      for (const path of sortedResolvedKeys) {{
        const blobUrl = allResolvedBlobs[path];
        htmlContent = htmlContent.split("./" + path).join(blobUrl);
        htmlContent = htmlContent.split("/" + path).join(blobUrl);
        htmlContent = htmlContent.split(path).join(blobUrl);
      }}

      const finalBlob = new Blob([htmlContent], {{ type: "text/html" }});
      iframe.src = URL.createObjectURL(finalBlob);
    }}
  </script>
</body>
</html>
"""
