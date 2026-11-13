//! 系统登录项（开机自启）同步。
//!
//! [INPUT]
//! - tauri_plugin_autostart (POS: 平台登录项；macOS LaunchAgent、Windows Run 键、Linux autostart 条目)
//! - 设置项 `auto_launch_at_login` (POS: 用户期望的开关)
//!
//! [OUTPUT]
//! - sync_login_item: 让系统登录项与开关一致；开发构建一律不碰
//!
//! [POS]
//! 系统登录项的唯一写入口：启动、保存设置、重置设置三处都经由这里。

use tauri::{AppHandle, Runtime};
use tauri_plugin_autostart::{AutoLaunchManager, Error, ManagerExt};

/// 同步策略需要的三个登录项操作；抽成 trait 让策略可以脱离真实系统测试。
trait LoginItem {
    fn is_enabled(&self) -> Result<bool, Error>;
    fn enable(&self) -> Result<(), Error>;
    fn disable(&self) -> Result<(), Error>;
}

impl LoginItem for AutoLaunchManager {
    fn is_enabled(&self) -> Result<bool, Error> {
        AutoLaunchManager::is_enabled(self)
    }

    fn enable(&self) -> Result<(), Error> {
        AutoLaunchManager::enable(self)
    }

    fn disable(&self) -> Result<(), Error> {
        AutoLaunchManager::disable(self)
    }
}

/// 让系统登录项与 `want` 一致。
pub(crate) fn sync_login_item<R: Runtime>(app: &AppHandle<R>, want: bool) {
    apply(&*app.autolaunch(), cfg!(debug_assertions), want);
}

fn apply(item: &impl LoginItem, development_build: bool, want: bool) {
    // 登录项写的是「当前运行的二进制路径」，且只在条目不存在时才写入、之后不会被校正。开发构建
    // 从工作区运行（`cargo tauri dev`、`target/debug`），它的二进制随时被重编或删除：一旦它抢先
    // 登记，之后安装的正式版也无法把登录项改回来，每次登录系统都会去启动一个陈旧的开发构建。
    if development_build {
        println!("🔧 Development build: the OS login item is left untouched");
        return;
    }

    let registered = match item.is_enabled() {
        Ok(registered) => registered,
        Err(err) => {
            eprintln!("⚠️ Could not read the OS login item: {err}");
            return;
        }
    };
    let (changed_to, result) = match (want, registered) {
        (true, false) => ("enabled", item.enable()),
        (false, true) => ("disabled", item.disable()),
        _ => return,
    };
    match result {
        Ok(()) => println!("✅ Auto-launch {changed_to} at login"),
        Err(err) => eprintln!("⚠️ Could not change the OS login item: {err}"),
    }
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;

    use super::{apply, Error, LoginItem};

    /// 记录收到的每个调用；`registered` 为 `None` 表示读取登录项失败。
    #[derive(Default)]
    struct FakeLoginItem {
        registered: Option<bool>,
        write_fails: bool,
        calls: RefCell<Vec<&'static str>>,
    }

    impl FakeLoginItem {
        fn record(&self, call: &'static str) -> Result<(), Error> {
            self.calls.borrow_mut().push(call);
            if self.write_fails && call != "is_enabled" {
                return Err(Error::Anyhow("write refused".to_string()));
            }
            Ok(())
        }
    }

    impl LoginItem for FakeLoginItem {
        fn is_enabled(&self) -> Result<bool, Error> {
            self.record("is_enabled")?;
            self.registered
                .ok_or_else(|| Error::Anyhow("unreadable".to_string()))
        }

        fn enable(&self) -> Result<(), Error> {
            self.record("enable")
        }

        fn disable(&self) -> Result<(), Error> {
            self.record("disable")
        }
    }

    fn calls(development_build: bool, want: bool, registered: Option<bool>) -> Vec<&'static str> {
        let item = FakeLoginItem {
            registered,
            ..Default::default()
        };
        apply(&item, development_build, want);
        item.calls.into_inner()
    }

    /// 开发构建既不读也不写：任何开关、任何现有条目状态下都零调用。
    #[test]
    fn a_development_build_never_touches_the_login_item() {
        for want in [true, false] {
            for registered in [Some(true), Some(false), None] {
                assert!(
                    calls(true, want, registered).is_empty(),
                    "want={want} registered={registered:?}"
                );
            }
        }
    }

    #[test]
    fn a_release_build_makes_the_login_item_follow_the_setting() {
        assert_eq!(calls(false, true, Some(false)), ["is_enabled", "enable"]);
        assert_eq!(calls(false, false, Some(true)), ["is_enabled", "disable"]);
    }

    #[test]
    fn a_login_item_that_already_matches_is_not_rewritten() {
        assert_eq!(calls(false, true, Some(true)), ["is_enabled"]);
        assert_eq!(calls(false, false, Some(false)), ["is_enabled"]);
    }

    #[test]
    fn an_unreadable_login_item_is_left_alone() {
        for want in [true, false] {
            assert_eq!(calls(false, want, None), ["is_enabled"]);
        }
    }

    #[test]
    fn a_refused_write_is_attempted_once_and_does_not_panic() {
        let item = FakeLoginItem {
            registered: Some(false),
            write_fails: true,
            ..Default::default()
        };
        apply(&item, false, true);
        assert_eq!(item.calls.into_inner(), ["is_enabled", "enable"]);
    }
}
