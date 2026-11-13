//! 桌面壳与后端共用的数据根目录解析
//!
//! [INPUT]
//! - 环境变量 `MYRM_DESKTOP_DATA_DIR`（显式指定，任何构建都生效）
//! - `SystemConfig.custom_data_dir`（持久化设置；设置文件与已安装的正式版共用）
//! - 构建类型（`debug_assertions`）与用户主目录
//!
//! [OUTPUT]
//! - `override_dir`: 传给后端 `MYRM_DATA_DIR` 的目录，`None` 表示后端默认的 `~/.myrm`
//! - `effective_dir`: 数据迁移、故障恢复等壳内操作所用的同一个目录
//! - `is_pinned`: 目录由环境变量或开发构建固定，设置里的目录迁移不适用
//!
//! [POS]
//! 壳内数据目录的唯一解析点：后端启动、数据迁移、故障恢复必须作用于同一个目录。

use std::path::{Path, PathBuf};

const ENV_VAR: &str = "MYRM_DESKTOP_DATA_DIR";
const DEFAULT_DIR_NAME: &str = ".myrm";
/// 开发构建在没有显式指定时使用的目录。与真实用户的 `~/.myrm` 分开，
/// 两个服务不会去写同一个 SQLite 文件。
const DEVELOPMENT_DIR_NAME: &str = ".myrm-desktop-dev";

/// 用户主目录；取不到时退回当前目录。
pub fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn explicit(env_value: Option<&str>) -> Option<String> {
    env_value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
}

fn override_for(
    env_value: Option<&str>,
    persisted: Option<&str>,
    development_build: bool,
    home: &Path,
) -> Option<String> {
    if let Some(dir) = explicit(env_value) {
        return Some(dir);
    }
    if development_build {
        // 持久化设置里的目录属于真实用户的数据，开发构建不去打开它。
        return Some(
            home.join(DEVELOPMENT_DIR_NAME)
                .to_string_lossy()
                .into_owned(),
        );
    }
    persisted.map(str::to_owned)
}

fn effective_for(
    env_value: Option<&str>,
    persisted: Option<&str>,
    development_build: bool,
    home: &Path,
) -> PathBuf {
    override_for(env_value, persisted, development_build, home)
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(DEFAULT_DIR_NAME))
}

fn is_pinned_for(env_value: Option<&str>, development_build: bool) -> bool {
    development_build || explicit(env_value).is_some()
}

fn env_value() -> Option<String> {
    std::env::var(ENV_VAR).ok()
}

pub fn override_dir(persisted: Option<&str>) -> Option<String> {
    override_for(
        env_value().as_deref(),
        persisted,
        cfg!(debug_assertions),
        &home_dir(),
    )
}

pub fn effective_dir(persisted: Option<&str>) -> PathBuf {
    effective_for(
        env_value().as_deref(),
        persisted,
        cfg!(debug_assertions),
        &home_dir(),
    )
}

pub fn is_pinned() -> bool {
    is_pinned_for(env_value().as_deref(), cfg!(debug_assertions))
}

#[cfg(test)]
mod tests {
    use super::*;

    const HOME: &str = "/home/user";
    const REAL_CUSTOM: &str = "/data/real-user-choice";

    fn home() -> &'static Path {
        Path::new(HOME)
    }

    #[test]
    fn an_explicit_environment_value_wins_in_every_build() {
        for development_build in [false, true] {
            assert_eq!(
                override_for(
                    Some("/tmp/e2e"),
                    Some(REAL_CUSTOM),
                    development_build,
                    home()
                ),
                Some("/tmp/e2e".to_string())
            );
        }
    }

    #[test]
    fn a_blank_environment_value_counts_as_unset() {
        assert_eq!(override_for(Some("  "), None, false, home()), None);
        assert_eq!(override_for(Some(""), None, false, home()), None);
        assert_eq!(explicit(Some("  /tmp/e2e  ")), Some("/tmp/e2e".to_string()));
    }

    #[test]
    fn a_release_build_keeps_the_saved_setting_or_the_backend_default() {
        assert_eq!(
            override_for(None, Some(REAL_CUSTOM), false, home()),
            Some(REAL_CUSTOM.to_string())
        );
        assert_eq!(override_for(None, None, false, home()), None);
        assert_eq!(
            effective_for(None, None, false, home()),
            PathBuf::from("/home/user/.myrm")
        );
    }

    #[test]
    fn a_development_build_never_defaults_to_the_real_users_directory() {
        let expected = PathBuf::from("/home/user/.myrm-desktop-dev");
        assert_eq!(effective_for(None, None, true, home()), expected);
        // The saved setting is shared with an installed release app, so it is not followed either.
        assert_eq!(
            effective_for(None, Some(REAL_CUSTOM), true, home()),
            expected
        );
        assert_ne!(expected, home().join(DEFAULT_DIR_NAME));
    }

    #[test]
    fn the_directory_is_pinned_by_a_development_build_or_the_environment_only() {
        assert!(!is_pinned_for(None, false));
        assert!(!is_pinned_for(Some("  "), false));
        assert!(is_pinned_for(Some("/tmp/e2e"), false));
        assert!(is_pinned_for(None, true));
        assert!(is_pinned_for(Some("/tmp/e2e"), true));
    }
}
