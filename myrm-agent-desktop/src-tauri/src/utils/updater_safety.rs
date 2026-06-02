//! Tauri Updater 公钥安全校验
//!
//! ⚠️ 自更新提示：一旦我被更新，务必更新：
//! 1. 本文件的 INPUT/OUTPUT/POS 注释
//! 2. 所属文件夹的 _ARCH.md
//!
//! [INPUT]
//! - 编译时嵌入的 `tauri.conf.json` 内容（通过 `include_str!`）
//!
//! [OUTPUT]
//! - `UpdaterPubkeySafety` 校验结果（Safe / PlaceholderDev / PlaceholderProd / Invalid）
//! - 控制台醒目警告（dev 模式）或 panic（production 模式）
//!
//! [POS]
//! Tauri Updater plugin 在编译时把 `tauri.conf.json#plugins.updater.pubkey`
//! 写入二进制。如果该值仍是占位符，OTA 更新会失败且可能被供应链攻击伪造
//! 升级包。本模块在启动期强校验占位符状态：
//! - Dev build：输出醒目警告但允许继续（开发者可以本地无 pubkey 调试）
//! - Production build：返回错误，由调用方决定是否阻断启动（推荐阻断）
//!
//! 占位符识别规则：包含 `PLACEHOLDER` 子串或为空字符串均视为未配置。

const TAURI_CONFIG_JSON: &str = include_str!("../../tauri.conf.json");
const PLACEHOLDER_SENTINEL: &str = "PLACEHOLDER";

/// Updater pubkey 安全等级
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UpdaterPubkeySafety {
    /// 配置了真实 pubkey，OTA 安全可用
    Safe,
    /// Dev 模式下检测到占位符（警告但允许）
    PlaceholderDev,
    /// Production 模式下检测到占位符（必须阻断）
    PlaceholderProd,
    /// 配置无效或解析失败
    Invalid(String),
}

/// 校验编译时嵌入的 Tauri Updater pubkey 是否安全可用
///
/// 此函数在应用启动早期调用（main.rs setup 中），用于尽早发现
/// pubkey 占位符状态，避免：
/// 1. 生产环境 OTA 更新失败导致用户长期停留在旧版本
/// 2. 供应链攻击者伪造升级包通过 placeholder pubkey 静默植入
///
/// # 行为说明
/// - `Safe`：pubkey 合法，OTA 可用
/// - `PlaceholderDev`：dev 构建检测到占位符，输出警告但允许继续
/// - `PlaceholderProd`：production 构建检测到占位符，强烈建议阻断启动
/// - `Invalid`：tauri.conf.json 解析失败或 pubkey 字段缺失，配置损坏
pub fn check_updater_pubkey_safety() -> UpdaterPubkeySafety {
    let config: serde_json::Value = match serde_json::from_str(TAURI_CONFIG_JSON) {
        Ok(v) => v,
        Err(e) => return UpdaterPubkeySafety::Invalid(format!("parse tauri.conf.json failed: {e}")),
    };

    let pubkey = match config
        .pointer("/plugins/updater/pubkey")
        .and_then(|v| v.as_str())
    {
        Some(s) => s,
        None => {
            return UpdaterPubkeySafety::Invalid(
                "plugins.updater.pubkey not found in tauri.conf.json".to_string(),
            );
        }
    };

    let is_placeholder = pubkey.is_empty() || pubkey.contains(PLACEHOLDER_SENTINEL);

    if !is_placeholder {
        return UpdaterPubkeySafety::Safe;
    }

    if cfg!(debug_assertions) {
        emit_dev_warning(pubkey);
        UpdaterPubkeySafety::PlaceholderDev
    } else {
        emit_prod_error(pubkey);
        UpdaterPubkeySafety::PlaceholderProd
    }
}

fn emit_dev_warning(pubkey: &str) {
    eprintln!("⚠️  ════════════════════════════════════════════════════════════════════");
    eprintln!("⚠️  Tauri Updater pubkey 为占位符: {pubkey}");
    eprintln!("⚠️  OTA 自动更新功能在当前 dev 构建中已被运行时禁用。");
    eprintln!("⚠️  ");
    eprintln!("⚠️  生产发布前必须执行以下步骤：");
    eprintln!(
        "⚠️    1. cd myrm-agent-desktop && bun x @tauri-apps/cli signer generate \\"
    );
    eprintln!("⚠️         -w ~/.tauri/myrmagent.key");
    eprintln!("⚠️    2. 将公钥粘贴到 tauri.conf.json#plugins.updater.pubkey");
    eprintln!("⚠️    3. 将私钥内容和 passphrase 设为 GitHub Secret：");
    eprintln!("⚠️         TAURI_SIGNING_PRIVATE_KEY");
    eprintln!("⚠️         TAURI_SIGNING_PRIVATE_KEY_PASSWORD");
    eprintln!("⚠️  ");
    eprintln!("⚠️  详细流程见 myrm-agent-desktop/SIGNING.md");
    eprintln!("⚠️  ════════════════════════════════════════════════════════════════════");
}

fn emit_prod_error(pubkey: &str) {
    eprintln!("❌  ════════════════════════════════════════════════════════════════════");
    eprintln!("❌  CRITICAL: Production build with placeholder Updater pubkey: {pubkey}");
    eprintln!("❌  This is a supply-chain security risk. Refusing to enable OTA updates.");
    eprintln!("❌  ");
    eprintln!("❌  See myrm-agent-desktop/SIGNING.md for the key generation procedure.");
    eprintln!("❌  ════════════════════════════════════════════════════════════════════");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_placeholder_keyword() {
        let value = serde_json::json!({
            "plugins": {
                "updater": {
                    "pubkey": "UNSAFE_UPDATER_PUBKEY_PLACEHOLDER_GENERATE_BEFORE_RELEASE"
                }
            }
        });
        let pubkey = value
            .pointer("/plugins/updater/pubkey")
            .and_then(|v| v.as_str())
            .unwrap();
        assert!(pubkey.contains(PLACEHOLDER_SENTINEL));
    }

    #[test]
    fn detects_empty_pubkey() {
        let value = serde_json::json!({
            "plugins": { "updater": { "pubkey": "" } }
        });
        let pubkey = value
            .pointer("/plugins/updater/pubkey")
            .and_then(|v| v.as_str())
            .unwrap();
        assert!(pubkey.is_empty());
    }

    #[test]
    fn accepts_real_pubkey() {
        let value = serde_json::json!({
            "plugins": {
                "updater": {
                    "pubkey": "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk="
                }
            }
        });
        let pubkey = value
            .pointer("/plugins/updater/pubkey")
            .and_then(|v| v.as_str())
            .unwrap();
        assert!(!pubkey.is_empty());
        assert!(!pubkey.contains(PLACEHOLDER_SENTINEL));
    }
}
