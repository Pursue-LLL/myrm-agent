//! Updater 签名安全态只读查询（信任徽章数据源）。
//!
//! [INPUT]
//! - crate::utils::updater_safety::check_updater_pubkey_safety (POS: 编译期 pubkey 强校验)
//!
//! [OUTPUT]
//! - `get_updater_safety`: 返回 `safe` / `placeholder_dev` / `placeholder_prod` / `invalid`
//!
//! [POS]
//! 纯只读呈现层，不触碰校验逻辑；供前端 About 信任徽章展示签名状态。

use crate::utils::updater_safety::{check_updater_pubkey_safety, UpdaterPubkeySafety};

/// 查询当前构建的 Updater 签名安全态（只读，不触发校验副作用之外的任何行为）。
#[tauri::command]
pub fn get_updater_safety() -> Result<String, String> {
    Ok(match check_updater_pubkey_safety() {
        UpdaterPubkeySafety::Safe => "safe".to_string(),
        UpdaterPubkeySafety::PlaceholderDev => "placeholder_dev".to_string(),
        UpdaterPubkeySafety::PlaceholderProd => "placeholder_prod".to_string(),
        UpdaterPubkeySafety::Invalid(_) => "invalid".to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safety_status_maps_to_stable_strings() {
        let mapped = |safety: UpdaterPubkeySafety| match safety {
            UpdaterPubkeySafety::Safe => "safe",
            UpdaterPubkeySafety::PlaceholderDev => "placeholder_dev",
            UpdaterPubkeySafety::PlaceholderProd => "placeholder_prod",
            UpdaterPubkeySafety::Invalid(_) => "invalid",
        };
        assert_eq!(mapped(UpdaterPubkeySafety::Safe), "safe");
        assert_eq!(
            mapped(UpdaterPubkeySafety::PlaceholderDev),
            "placeholder_dev"
        );
        assert_eq!(
            mapped(UpdaterPubkeySafety::PlaceholderProd),
            "placeholder_prod"
        );
        assert_eq!(
            mapped(UpdaterPubkeySafety::Invalid("x".to_string())),
            "invalid"
        );
    }

    #[test]
    fn live_check_returns_known_state() {
        let state = get_updater_safety().expect("command must succeed");
        assert!(
            ["safe", "placeholder_dev", "placeholder_prod", "invalid"].contains(&state.as_str()),
            "unexpected state: {state}"
        );
    }
}
