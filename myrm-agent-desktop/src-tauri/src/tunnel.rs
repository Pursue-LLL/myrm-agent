//! Quick Tunnel helpers — process lifecycle is owned by myrm-agent-server.

use std::time::Duration;

use tauri::{AppHandle, Manager};

/// Resolve bundled cloudflared sidecar path for the Python backend.
pub fn resolve_cloudflared_path(app: &AppHandle) -> Result<String, String> {
    let binary_name = if cfg!(target_os = "windows") {
        "binaries/cloudflared-x86_64-pc-windows-msvc.exe"
    } else if cfg!(target_arch = "aarch64") {
        "binaries/cloudflared-aarch64-apple-darwin"
    } else {
        "binaries/cloudflared-x86_64-apple-darwin"
    };

    let path = app
        .path()
        .resolve(binary_name, tauri::path::BaseDirectory::Resource)
        .map_err(|e| format!("Failed to resolve cloudflared path: {}", e))?;

    if !path.exists() {
        return Err(format!("cloudflared binary not found at {:?}", path));
    }

    Ok(path.to_string_lossy().into_owned())
}

/// Ask the local Server API to stop an active Quick Tunnel.
pub async fn stop_quick_tunnel_via_backend(api_port: u16) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            println!("Failed to build HTTP client for tunnel stop: {}", e);
            return;
        }
    };

    let url = format!("http://127.0.0.1:{}/api/v1/system/tunnel/stop", api_port);
    match client.post(&url).send().await {
        Ok(response) if response.status().is_success() => {
            println!("Quick Tunnel stopped via Server API");
        }
        Ok(response) => {
            println!(
                "Quick Tunnel stop API returned HTTP {}",
                response.status()
            );
        }
        Err(e) => {
            println!("Quick Tunnel stop API request failed: {}", e);
        }
    }
}
