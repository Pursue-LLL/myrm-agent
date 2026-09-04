"""Crypto packaging utilities for secure static artifact publishing.

[POS] Encrypts multi-file static artifacts into an in-memory VFS encrypted bundle
wrapped with a zero-dependency Web Crypto AES-256-GCM HTML bootstrap shell.

[INPUT]
- dict[str, PublishFile]: Raw static files for the artifact
- str: User provided password

[OUTPUT]
- dict[str, PublishFile]: Single index.html containing encrypted payload + decryptor shell
"""

from __future__ import annotations

import base64
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.services.hosting.packager import PublishFile

PBKDF2_ITERATIONS = 100_000
SALT_BYTES = 16
NONCE_BYTES = 12


def _derive_aes_key(password: str, salt: bytes) -> bytes:
    """Derive 256-bit AES-GCM key from password and salt via PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt_payload(payload_bytes: bytes, password: str) -> dict[str, str]:
    """Encrypt byte payload with AES-256-GCM using a PBKDF2-derived key."""
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = _derive_aes_key(password, salt)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, payload_bytes, None)

    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "iterations": str(PBKDF2_ITERATIONS),
    }


def _decrypt_payload(encrypted_dict: dict[str, str], password: str) -> bytes:
    """Decrypt byte payload from encrypted dict (used for self-verification tests)."""
    salt = base64.b64decode(encrypted_dict["salt"])
    nonce = base64.b64decode(encrypted_dict["nonce"])
    ciphertext = base64.b64decode(encrypted_dict["ciphertext"])
    iterations = int(encrypted_dict.get("iterations", PBKDF2_ITERATIONS))

    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    key = kdf.derive(password.encode("utf-8"))
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def _render_decryptor_html(encrypted_data: dict[str, str], title: str = "Protected Artifact") -> str:
    """Generate standalone HTML decryptor shell using browser-native Web Crypto API."""
    data_json = json.dumps(encrypted_data)
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

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
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
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
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 0.75rem;
      color: #fff;
      font-size: 0.95rem;
      outline: none;
      transition: all 0.2s;
    }}
    input[type="password"]:focus {{
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
    }}
    button {{
      width: 100%;
      padding: 0.75rem 1rem;
      background: #0284c7;
      color: #fff;
      border: none;
      border-radius: 0.75rem;
      font-size: 0.95rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
    }}
    button:hover {{ background: #0369a1; }}
    button:active {{ transform: scale(0.99); }}
    button:disabled {{ background: #374151; cursor: not-allowed; }}
    .error {{
      margin-top: 1rem;
      font-size: 0.825rem;
      color: #f87171;
      display: none;
    }}
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
      <div class="error" id="error-msg">Incorrect password or corrupted data.</div>
      <div class="error" id="env-error-msg" style="color: #fbbf24; text-align: left; line-height: 1.4; border: 1px solid rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.1); padding: 0.75rem; border-radius: 0.5rem; display: none;"></div>
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
          envErr.textContent = "Security Notice: Web Cryptography requires a Secure Context (HTTPS or localhost). If you are viewing over plain HTTP, please access via HTTPS or save this file and open it locally in your browser.";
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
      const password = input.value;
      if (!password) return;

      if (!checkSecureContext()) return;

      btn.disabled = true;
      btn.textContent = "Decrypting...";
      error.style.display = "none";

      try {{
        const salt = b64ToBuf(encryptedData.salt);
        const nonce = b64ToBuf(encryptedData.nonce);
        const ciphertext = b64ToBuf(encryptedData.ciphertext);
        const iterations = parseInt(encryptedData.iterations || "100000", 10);

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
      document.body.style.background = "#fff";
      const iframe = document.getElementById("app-container");
      iframe.style.display = "block";

      const entryFile = vfs["index.html"] || vfs[Object.keys(vfs).find(k => k.endsWith(".html"))];
      if (!entryFile) {{
        document.body.innerHTML = "<p style='padding:2rem;color:red'>No entry HTML found in bundle.</p>";
        return;
      }}

      let htmlContent = entryFile.encoding === "base64" ? atob(entryFile.content) : entryFile.content;

      // Replace static assets with Blob URLs in HTML (sorted by descending length to prevent partial prefix replacement)
      const assetKeys = Object.keys(vfs)
        .filter(k => k !== "index.html" && !k.endsWith(".html"))
        .sort((a, b) => b.length - a.length);

      for (const path of assetKeys) {{
        const file = vfs[path];
        let mime = "application/octet-stream";
        if (path.endsWith(".css")) mime = "text/css";
        else if (path.endsWith(".js") || path.endsWith(".mjs")) mime = "application/javascript";
        else if (path.endsWith(".json")) mime = "application/json";
        else if (path.endsWith(".svg")) mime = "image/svg+xml";
        else if (path.endsWith(".png")) mime = "image/png";
        else if (path.endsWith(".jpg") || path.endsWith(".jpeg")) mime = "image/jpeg";
        else if (path.endsWith(".webp")) mime = "image/webp";

        let blob;
        if (file.encoding === "base64") {{
          blob = new Blob([b64ToBuf(file.content)], {{ type: mime }});
        }} else {{
          blob = new Blob([file.content], {{ type: mime }});
        }}
        const blobUrl = URL.createObjectURL(blob);
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


def package_encrypted_publish_files(
    files: dict[str, PublishFile],
    password: str,
    *,
    title: str = "Protected Artifact",
) -> dict[str, PublishFile]:
    """Package multi-file artifact into a single encrypted deployable index.html payload."""
    if not password:
        return files

    vfs_dict: dict[str, dict[str, str]] = {}
    for entry_name, pfile in files.items():
        vfs_dict[entry_name] = {
            "content": pfile.content,
            "encoding": pfile.encoding,
        }

    raw_json_bytes = json.dumps(vfs_dict, ensure_ascii=False).encode("utf-8")
    encrypted_dict = _encrypt_payload(raw_json_bytes, password)
    shell_html = _render_decryptor_html(encrypted_dict, title=title)

    return {
        "index.html": PublishFile(
            path="index.html",
            content=shell_html,
            encoding="utf-8",
        )
    }
