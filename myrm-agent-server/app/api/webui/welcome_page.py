"""The page shown in the browser when the WebUI server has started.

[INPUT]
- str, int: the host and port the QR code and the page's address point at

[OUTPUT]
- render_welcome_page: one self-contained HTML document with the access QR code, an Open WebUI button and a QR download

[POS]
The page ``uvicorn_runner`` opens at start-up and a phone reaches by the QR code. It writes the host into a text node, an
attribute and a script string, so each use is encoded for its own context here and the page cannot be given markup by
whoever built the host.
"""

from __future__ import annotations

import html
import json
from string import Template
from urllib.parse import urlencode

_PAGE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyrmAgent - WebUI Ready</title>
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.container {
  background: #ffffff;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  padding: 50px;
  max-width: 700px;
  text-align: center;
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

h1 {
  font-size: 3rem;
  margin-bottom: 20px;
  color: #333333;
  font-weight: 700;
}

.subtitle {
  font-size: 1.2rem;
  color: #666666;
  margin-bottom: 40px;
}

.qr-section {
  margin: 40px 0;
  padding: 40px;
  background: #f1f3f5;
  border-radius: 15px;
}

.qr-section h2 {
  font-size: 1.8rem;
  margin-bottom: 25px;
  color: #555555;
  font-weight: 600;
}

.qr-section img {
  width: 300px;
  height: 300px;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  background: #ffffff;
  padding: 15px;
}

.url {
  margin-top: 25px;
  font-size: 1.2rem;
  color: #4c51bf;
  font-weight: 600;
  word-break: break-all;
  font-family: 'Monaco', 'Consolas', monospace;
}

.actions {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 40px;
  flex-wrap: wrap;
}

button {
  padding: 18px 35px;
  font-size: 1.1rem;
  font-weight: 600;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

button:focus-visible {
  outline: 3px solid #4c51bf;
  outline-offset: 3px;
}

.btn-primary {
  background: #4c51bf;
  color: #ffffff;
}

.btn-primary:hover {
  background: #434190;
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(76, 81, 191, 0.4);
}

.btn-secondary {
  background: #ffffff;
  color: #4c51bf;
  border: 2px solid #4c51bf;
}

.btn-secondary:hover {
  background: #f1f3f5;
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
}

.info {
  margin-top: 40px;
  padding: 25px;
  background: #e7f3ff;
  border-radius: 12px;
  color: #0057b3;
  font-size: 1rem;
  line-height: 1.6;
  border-left: 4px solid #4c51bf;
}

.info strong {
  font-weight: 700;
}

@media (max-width: 640px) {
  .container {
    padding: 30px 20px;
  }

  h1 {
    font-size: 2rem;
  }

  .qr-section img {
    width: 250px;
    height: 250px;
  }

  .actions {
    flex-direction: column;
  }

  button {
    width: 100%;
  }
}
</style>
</head>
<body>
<div class="container">
  <h1>🚀 WebUI is Ready!</h1>
  <p class="subtitle">Scan the QR code to access on your mobile device</p>

  <div class="qr-section">
    <h2>📱 Scan to Access</h2>
    <img src="$qr_src_attribute" alt="QR Code">
    <p class="url">$url_text</p>
  </div>

  <div class="actions">
    <button class="btn-primary" onclick="location.href='/'">
      Open WebUI
    </button>
    <button class="btn-secondary" onclick="downloadQRCode()">
      📥 Download QR Code
    </button>
  </div>

  <div class="info">
    <strong>Tip:</strong> Desktop and WebUI modes share the same database.
    Your configurations and chat history are synchronized across all devices!
  </div>
</div>

<script>
  function downloadQRCode() {
    const link = document.createElement('a');
    link.href = $qr_src_script;
    link.download = 'myrmagent-webui-qrcode.png';
    link.click();
  }
</script>
</body>
</html>
""")


def render_welcome_page(host: str, port: int) -> str:
    """The welcome page for ``http://{host}:{port}``, with every use of the address encoded for where it lands."""
    qr_src = "/api/v1/webui/qrcode.png?" + urlencode({"host": host, "port": port})
    return _PAGE.substitute(
        qr_src_attribute=html.escape(qr_src),
        qr_src_script=json.dumps(qr_src),
        url_text=html.escape(f"http://{host}:{port}"),
    )
