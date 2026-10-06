//! Login credential storage for Locked Use (platform keychain).
//!
//! The Python server reads this entry with `security find-generic-password` when
//! it has to unlock the screen for a Computer Use session; the desktop shell only
//! stores, checks and deletes it. The password reaches `security` over stdin
//! (`security -i`) because the argv of every process is readable by the same user
//! through `ps`.
//!
//! [INPUT]
//! - macOS `security` CLI (POS: system keychain command line; `-i` reads its commands from stdin)
//!
//! [OUTPUT]
//! - store_password / has_stored_password / delete_password: login-password keychain access
//! - CredentialError: failure type of those operations
//!
//! [POS]
//! Credential primitives behind `commands::screen_lock`. The keychain service and
//! account names are a cross-process contract with the server's `MacScreenUnlocker`
//! (pinned by `test_keychain_and_curtain_contract.py`).

#[derive(Debug, thiserror::Error)]
pub enum CredentialError {
    #[error("credential operation failed: {0}")]
    OperationFailed(String),
    #[error("credential storage is not supported on this platform")]
    #[allow(dead_code)]
    UnsupportedPlatform,
}

/// Store the user's login password in the platform keychain.
pub fn store_password(password: &str) -> Result<(), CredentialError> {
    platform::store(password)
}

/// Check whether a password is stored in the platform keychain.
pub fn has_stored_password() -> bool {
    platform::has_password()
}

/// Delete the stored password; an absent entry counts as deleted.
pub fn delete_password() -> Result<(), CredentialError> {
    platform::delete()
}

#[cfg(target_os = "macos")]
mod platform {
    use super::CredentialError;
    use std::io::Write;
    use std::process::{Command, Stdio};

    const KEYCHAIN_SERVICE: &str = "com.myrm.agent.screen-unlock";
    const KEYCHAIN_ACCOUNT: &str = "login-password";
    /// `security` exit status for "item not found".
    const EXIT_ITEM_NOT_FOUND: i32 = 44;

    pub fn store(password: &str) -> Result<(), CredentialError> {
        store_item(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, password)
    }

    pub fn has_password() -> bool {
        has_item(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    }

    pub fn delete() -> Result<(), CredentialError> {
        delete_item(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    }

    /// Quote one argument for `security -i`: its line parser groups on double
    /// quotes and honours backslash escapes inside them.
    fn quote_interactive_arg(arg: &str) -> String {
        let mut quoted = String::with_capacity(arg.len() + 2);
        quoted.push('"');
        for ch in arg.chars() {
            if matches!(ch, '"' | '\\') {
                quoted.push('\\');
            }
            quoted.push(ch);
        }
        quoted.push('"');
        quoted
    }

    /// One interactive-mode line that adds the item, or updates it in place.
    fn add_item_command(service: &str, account: &str, password: &str) -> String {
        format!(
            "add-generic-password -s {} -a {} -w {} -U\n",
            quote_interactive_arg(service),
            quote_interactive_arg(account),
            quote_interactive_arg(password),
        )
    }

    /// `security -i` reads its commands from stdin, so secrets never appear in argv.
    fn security_interactive() -> Command {
        let mut command = Command::new("security");
        command.arg("-i");
        command
    }

    fn failed(action: &str, error: impl std::fmt::Display) -> CredentialError {
        CredentialError::OperationFailed(format!("keychain {action} failed: {error}"))
    }

    /// Add the item, or update it in place (a failed update keeps the old password).
    ///
    /// Failures report the exit status only: `security` may echo fragments of a
    /// malformed command line, which here contains the password.
    fn store_item(service: &str, account: &str, password: &str) -> Result<(), CredentialError> {
        // The interactive protocol is line based: a control character would split
        // the command and store a truncated password.
        if password.chars().any(char::is_control) {
            return Err(CredentialError::OperationFailed(
                "password must not contain control characters".into(),
            ));
        }

        let mut child = security_interactive()
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| failed("store", e))?;
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| failed("store", "stdin unavailable"))?;
        let written = stdin.write_all(add_item_command(service, account, password).as_bytes());
        drop(stdin); // EOF ends the interactive session
        let status = child.wait().map_err(|e| failed("store", e))?;
        written.map_err(|e| failed("store", e))?;
        if !status.success() {
            return Err(failed("store", format!("security exited with {status}")));
        }
        Ok(())
    }

    fn has_item(service: &str, account: &str) -> bool {
        Command::new("security")
            .args(["find-generic-password", "-s", service, "-a", account])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
    }

    fn delete_item(service: &str, account: &str) -> Result<(), CredentialError> {
        let status = Command::new("security")
            .args(["delete-generic-password", "-s", service, "-a", account])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| failed("delete", e))?;
        match status.code() {
            Some(0) | Some(EXIT_ITEM_NOT_FOUND) => Ok(()),
            _ => Err(failed("delete", format!("security exited with {status}"))),
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::sync::Arc;
        use std::thread;

        /// Throwaway service name so live tests never touch the real credential.
        fn unique_service(tag: &str) -> String {
            format!("com.myrm.agent.test.{tag}.{}", std::process::id())
        }

        #[test]
        fn quote_wraps_and_escapes_quotes_and_backslashes() {
            for (raw, expected) in [
                ("plain", r#""plain""#),
                ("with space", r#""with space""#),
                (r#"a"b"#, r#""a\"b""#),
                (r"a\b", r#""a\\b""#),
                (r#"\""#, r#""\\\"""#),
                ("$HOME `x` ;#", r#""$HOME `x` ;#""#),
            ] {
                assert_eq!(quote_interactive_arg(raw), expected, "raw: {raw}");
            }
        }

        #[test]
        fn add_command_is_a_single_line_carrying_all_three_fields() {
            let command = add_item_command("svc", "acc", "pw");
            assert_eq!(
                command,
                "add-generic-password -s \"svc\" -a \"acc\" -w \"pw\" -U\n"
            );
            assert_eq!(command.matches('\n').count(), 1);
        }

        #[test]
        fn interactive_session_never_carries_the_secret_in_argv() {
            let command = security_interactive();
            let args: Vec<_> = command.get_args().collect();
            assert_eq!(args, ["-i"]);
        }

        #[test]
        fn control_characters_are_rejected_before_any_process_runs() {
            for password in ["a\nb", "a\rb", "a\0b", "a\tb"] {
                let error = store_item("svc", "acc", password).expect_err("must reject");
                assert!(
                    error.to_string().contains("control characters"),
                    "password: {password:?}"
                );
            }
        }

        #[test]
        #[ignore = "writes a throwaway item to the login keychain"]
        fn live_store_round_trips_hostile_characters() {
            let service = unique_service("roundtrip");
            let read_back = || {
                let output = Command::new("security")
                    .args(["find-generic-password", "-s", &service, "-a", "probe", "-w"])
                    .output()
                    .expect("security");
                String::from_utf8_lossy(&output.stdout)
                    .trim_end_matches('\n')
                    .to_string()
            };

            for password in [
                "plain",
                "with space",
                r#"quote"inside"#,
                r"back\slash",
                r#"both\"mix\\"#,
                "single'quote",
                "dollar$HOME `tick` ;semi #hash",
                " leading and trailing ",
            ] {
                store_item(&service, "probe", password).expect("store");
                assert_eq!(read_back(), password);
            }
            // `security -w` prints the UTF-8 bytes as hex once a password is not plain ASCII.
            store_item(&service, "probe", "密码é").expect("store unicode");
            assert_eq!(read_back(), "e5af86e7a081c3a9");

            assert!(has_item(&service, "probe"));
            delete_item(&service, "probe").expect("delete");
            assert!(!has_item(&service, "probe"));
            delete_item(&service, "probe").expect("deleting an absent item is fine");
        }

        #[test]
        #[ignore = "writes a throwaway item to the login keychain"]
        fn live_store_keeps_the_secret_out_of_the_process_list() {
            let service = unique_service("argv");
            let secret = format!("S3cr3t-{}", std::process::id());

            let stop = Arc::new(AtomicBool::new(false));
            let poller = {
                let stop = Arc::clone(&stop);
                let needle = secret.clone();
                thread::spawn(move || {
                    let mut seen = false;
                    while !stop.load(Ordering::Relaxed) {
                        let listing = Command::new("ps")
                            .args(["-ww", "-axo", "args="])
                            .output()
                            .expect("ps");
                        seen |= String::from_utf8_lossy(&listing.stdout).contains(&needle);
                    }
                    seen
                })
            };

            for _ in 0..15 {
                store_item(&service, "probe", &secret).expect("store");
            }
            stop.store(true, Ordering::Relaxed);
            let seen = poller.join().expect("poller");
            delete_item(&service, "probe").expect("delete");

            assert!(!seen, "password was visible in the process list");
        }
    }
}

#[cfg(not(target_os = "macos"))]
mod platform {
    use super::CredentialError;

    pub fn store(_password: &str) -> Result<(), CredentialError> {
        Err(CredentialError::UnsupportedPlatform)
    }

    pub fn has_password() -> bool {
        false
    }

    pub fn delete() -> Result<(), CredentialError> {
        Ok(())
    }
}
