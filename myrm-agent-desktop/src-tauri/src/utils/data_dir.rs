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
//! - `ensure_relocatable`: 目录由环境变量或开发构建固定时拒绝设置里的目录迁移
//!
//! [POS]
//! 壳内数据目录的唯一解析点：后端启动、数据迁移、故障恢复必须作用于同一个目录。

use std::path::{Path, PathBuf};

const ENV_VAR: &str = "MYRM_DESKTOP_DATA_DIR";
const DEFAULT_DIR_NAME: &str = ".myrm";
/// 开发构建在没有显式指定时使用的目录。与真实用户的 `~/.myrm` 分开，
/// 两个服务不会去写同一个 SQLite 文件。
const DEVELOPMENT_DIR_NAME: &str = ".myrm-desktop-dev";

/// 用户主目录：`HOME`，其次 `USERPROFILE`，都没有时退回当前目录。
fn home_from(home: Option<String>, user_profile: Option<String>) -> PathBuf {
    home.or(user_profile)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn home_dir() -> PathBuf {
    home_from(
        std::env::var("HOME").ok(),
        std::env::var("USERPROFILE").ok(),
    )
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

/// 目录被固定时迁移到别处没有意义：后端不会再读新目录，设置里写下的路径还会影响与之共用
/// 设置文件的已安装正式版。
fn ensure_relocatable_for(env_value: Option<&str>, development_build: bool) -> Result<(), String> {
    if development_build || explicit(env_value).is_some() {
        return Err(format!(
            "The data directory is fixed by {ENV_VAR} or a development build; migration is unavailable"
        ));
    }
    Ok(())
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

pub fn ensure_relocatable() -> Result<(), String> {
    ensure_relocatable_for(env_value().as_deref(), cfg!(debug_assertions))
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
    fn migration_is_refused_only_when_a_development_build_or_the_environment_fixes_the_directory() {
        assert_eq!(ensure_relocatable_for(None, false), Ok(()));
        assert_eq!(ensure_relocatable_for(Some("  "), false), Ok(()));
        for (env, development_build) in [
            (Some("/tmp/e2e"), false),
            (None, true),
            (Some("/tmp/e2e"), true),
        ] {
            let error = ensure_relocatable_for(env, development_build).unwrap_err();
            assert_eq!(
                error,
                "The data directory is fixed by MYRM_DESKTOP_DATA_DIR or a development build; migration is unavailable"
            );
        }
    }

    #[test]
    fn the_home_directory_is_home_then_userprofile_then_the_current_directory() {
        let some = |value: &str| Some(value.to_string());
        assert_eq!(home_from(some("/h"), some("/u")), PathBuf::from("/h"));
        assert_eq!(home_from(None, some("/u")), PathBuf::from("/u"));
        assert_eq!(home_from(None, None), PathBuf::from("."));
    }

    /// Tests always run as a development build, so the public entry points must agree with each
    /// other and with the backend configuration: the backend, the migration and the recovery
    /// commands all act on one directory, and it is never the saved real-user directory.
    #[cfg(debug_assertions)]
    #[test]
    fn the_backend_and_the_shell_resolve_to_one_directory_that_is_never_the_saved_one() {
        use crate::config::{BackendConfig, SystemConfig};

        let saved = SystemConfig {
            custom_data_dir: Some(REAL_CUSTOM.to_string()),
            ..Default::default()
        };
        let for_backend = BackendConfig::from_system_config(&saved).custom_data_dir;

        assert_eq!(for_backend, override_dir(Some(REAL_CUSTOM)));
        assert_ne!(for_backend.as_deref(), Some(REAL_CUSTOM));
        assert_eq!(
            effective_dir(Some(REAL_CUSTOM)),
            PathBuf::from(for_backend.expect("a development build always names a directory"))
        );
        assert!(ensure_relocatable().is_err());
    }
}
