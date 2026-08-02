//! Desktop `.myrmtheme` open-file bridge to the WebUI import flow.

use std::path::{Path, PathBuf};

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Url};

const MAX_THEME_PACKAGE_BYTES: u64 = 24 * 1024 * 1024;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ThemePackageOpenPayload {
    path: String,
    filename: String,
    data_base64: String,
}

fn is_myrmtheme_path(path: &Path) -> bool {
    path.extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("myrmtheme"))
}

fn filename_from_path(path: &Path) -> String {
    path.file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("theme.myrmtheme")
        .to_string()
}

pub fn emit_theme_package_open(app: &AppHandle, path: PathBuf) {
    if !is_myrmtheme_path(&path) {
        return;
    }
    let metadata = match std::fs::metadata(&path) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("Failed to stat theme package {}: {error}", path.display());
            return;
        }
    };
    if metadata.len() > MAX_THEME_PACKAGE_BYTES {
        eprintln!(
            "Theme package exceeds 24MB limit: {} ({} bytes)",
            path.display(),
            metadata.len()
        );
        return;
    }
    let bytes = match std::fs::read(&path) {
        Ok(content) => content,
        Err(error) => {
            eprintln!("Failed to read theme package {}: {error}", path.display());
            return;
        }
    };
    let payload = ThemePackageOpenPayload {
        path: path.to_string_lossy().into_owned(),
        filename: filename_from_path(&path),
        data_base64: STANDARD.encode(bytes),
    };
    if let Err(error) = app.emit("theme-package-open", payload) {
        eprintln!("Failed to emit theme-package-open: {error}");
    }
}

pub fn handle_open_urls(app: &AppHandle, urls: Vec<Url>) {
    for url in urls {
        if let Ok(path) = url.to_file_path() {
            emit_theme_package_open(app, path);
        }
    }
}

pub fn handle_startup_args(app: &AppHandle) {
    for arg in std::env::args().skip(1) {
        if arg.starts_with('-') {
            continue;
        }
        let path = PathBuf::from(arg);
        if path.is_file() && is_myrmtheme_path(&path) {
            emit_theme_package_open(app, path);
        }
    }
}
