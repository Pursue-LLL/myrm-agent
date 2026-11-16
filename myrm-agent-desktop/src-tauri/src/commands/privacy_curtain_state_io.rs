//! 帷幕状态文件的落盘原语：带重试的读取与原子整文件替换。
//!
//! [INPUT]
//! - std::fs (POS: 文件读取 / 写入 / 改名)
//!
//! [OUTPUT]
//! - Document / read_document: 读取结果三态（有内容 / 没有可用内容 / 读不到）
//! - replace_document: 原子整文件替换，返回是否真的落盘
//! - IO_RETRY_PAUSE: 瞬时 I/O 错误的重试间隔
//!
//! [POS]
//! 只管文本这一层：不认识 `CurtainState`，也不决定读不到时怎么办（那是 privacy_curtain_state.rs 的策略）。
//! 整文件原子替换让另一进程的读者永远读到完整文档；Windows 上另一进程恰在替换同一文件时，
//! 读 / 改名会短暂得到 PermissionDenied 之类的错误，所以读写都先短重试。
//! 重试只在出错时才睡眠，正常路径零开销，最坏约 90 ms。

use std::fs;
use std::io;
use std::path::Path;
use std::thread;
use std::time::Duration;

const IO_ATTEMPTS: u32 = 10;
pub(super) const IO_RETRY_PAUSE: Duration = Duration::from_millis(10);

/// 一次读取的结果。「没有可用内容」与「读不到」必须分开：前者是确定的空状态，后者是未知。
pub(super) enum Document {
    Text(String),
    /// 文件不存在或不是合法文本：重试不会让它变好，等价于没有状态。
    Empty,
    /// 瞬时错误重试耗尽：真实状态也许存在，只是此刻读不出来。
    Unreadable,
}

/// 以固定间隔重试 `op`，直到成功、遇到不该重试的错误或预算耗尽，返回最后一次结果。
fn retry<T>(
    pause: Duration,
    retryable: impl Fn(&io::Error) -> bool,
    mut op: impl FnMut() -> io::Result<T>,
) -> io::Result<T> {
    let mut attempt = 1;
    loop {
        match op() {
            Err(error) if attempt < IO_ATTEMPTS && retryable(&error) => {
                thread::sleep(pause);
                attempt += 1;
            }
            outcome => return outcome,
        }
    }
}

fn is_absent_or_invalid(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        io::ErrorKind::NotFound | io::ErrorKind::InvalidData
    )
}

pub(super) fn read_document(read: impl FnMut() -> io::Result<String>, pause: Duration) -> Document {
    match retry(pause, |error| !is_absent_or_invalid(error), read) {
        Ok(text) => Document::Text(text),
        Err(error) if is_absent_or_invalid(&error) => Document::Empty,
        Err(_) => Document::Unreadable,
    }
}

/// 整文件原子替换：server 并发读取，被截断的文档会被解析为空状态。
pub(super) fn replace_document(path: &Path, content: &str, pause: Duration) -> bool {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let temp_path = path.with_extension("json.tmp");
    let replaced = retry(
        pause,
        |_| true,
        || {
            fs::write(&temp_path, content)?;
            fs::rename(&temp_path, path)
        },
    );
    if replaced.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    replaced.is_ok()
}

#[cfg(test)]
mod tests {
    use super::{read_document, replace_document, retry, Document, IO_ATTEMPTS};
    use std::cell::Cell;
    use std::io;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    /// 注入错误的测试不需要等待。
    const NO_PAUSE: Duration = Duration::ZERO;
    /// 真实文件的写入：无错误时重试从不睡眠，这个间隔只在 Windows 出现瞬时拒绝时才花时间。
    const BRIEF_PAUSE: Duration = Duration::from_millis(5);

    /// 读取 `kind` 错误直到预算耗尽，返回读取结果与实际尝试次数。
    fn read_failing_with(kind: io::ErrorKind) -> (Document, u32) {
        let calls = Cell::new(0_u32);
        let document = read_document(
            || {
                calls.set(calls.get() + 1);
                Err(io::Error::from(kind))
            },
            NO_PAUSE,
        );
        (document, calls.get())
    }

    /// 文件不存在 / 内容不是合法文本是确定的「没有状态」：一次就定，不重试。
    #[test]
    fn a_missing_or_invalid_file_is_empty_and_is_not_retried() {
        for kind in [io::ErrorKind::NotFound, io::ErrorKind::InvalidData] {
            let (document, calls) = read_failing_with(kind);
            assert!(matches!(document, Document::Empty), "{kind:?}");
            assert_eq!(calls, 1, "{kind:?}");
        }
    }

    /// 其余错误都可能是瞬时的：重试到预算耗尽仍读不到，结论是「未知」而不是「空」。
    #[test]
    fn a_read_that_keeps_failing_is_unreadable_not_empty() {
        for kind in [
            io::ErrorKind::PermissionDenied,
            io::ErrorKind::Interrupted,
            io::ErrorKind::WouldBlock,
            io::ErrorKind::Other,
        ] {
            let (document, calls) = read_failing_with(kind);
            assert!(matches!(document, Document::Unreadable), "{kind:?}");
            assert_eq!(calls, IO_ATTEMPTS, "{kind:?}");
        }
    }

    /// Windows 上另一进程恰在替换文件时读会得到 PermissionDenied：重试后读到的是真实内容。
    #[test]
    fn a_transient_read_error_is_retried_until_the_real_content_comes_back() {
        let calls = Cell::new(0_u32);
        let document = read_document(
            || {
                calls.set(calls.get() + 1);
                if calls.get() <= 3 {
                    Err(io::Error::from(io::ErrorKind::PermissionDenied))
                } else {
                    Ok("real content".to_string())
                }
            },
            NO_PAUSE,
        );
        assert!(matches!(document, Document::Text(text) if text == "real content"));
        assert_eq!(calls.get(), 4);
    }

    #[test]
    fn replacing_a_document_leaves_no_temp_file_and_creates_the_directory() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("nested").join("curtain_state.json");

        for content in ["first", "second"] {
            assert!(replace_document(&path, content, BRIEF_PAUSE));
            assert_eq!(std::fs::read_to_string(&path).expect("read"), content);
        }

        let entries: Vec<_> = std::fs::read_dir(path.parent().expect("parent"))
            .expect("read_dir")
            .map(|entry| entry.expect("entry").file_name())
            .collect();
        assert_eq!(entries, ["curtain_state.json"]);
    }

    /// 目标位置被目录占住时改名永远失败：写入要报告失败，且不留下临时文件。
    #[test]
    fn a_replacement_that_keeps_failing_reports_it_and_leaves_no_temp_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        std::fs::create_dir(&path).expect("occupy the target");

        assert!(!replace_document(&path, "content", NO_PAUSE));

        assert!(path.is_dir());
        assert!(!path.with_extension("json.tmp").exists());
    }

    /// Windows 上读者在原子替换的瞬间会短暂得到 PermissionDenied：读者同样重试，
    /// 重试预算内一定读得到，且读到的永远是完整文档。
    #[test]
    fn concurrent_reader_never_sees_a_torn_document() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        let document =
            |round: u64| format!("{{\"round\":{round},\"padding\":\"{}\"}}", "x".repeat(256));
        assert!(replace_document(&path, &document(0), BRIEF_PAUSE));

        let stop = Arc::new(AtomicBool::new(false));
        let reader = {
            let (stop, path) = (Arc::clone(&stop), path.clone());
            thread::spawn(move || {
                let mut torn = 0_u32;
                while !stop.load(Ordering::Relaxed) {
                    let content = retry(BRIEF_PAUSE, |_| true, || std::fs::read_to_string(&path))
                        .expect("file readable within the retry budget");
                    if serde_json::from_str::<serde_json::Value>(&content).is_err() {
                        torn += 1;
                    }
                }
                torn
            })
        };
        for round in 1..3000_u64 {
            assert!(replace_document(&path, &document(round), BRIEF_PAUSE));
        }
        stop.store(true, Ordering::Relaxed);

        assert_eq!(
            reader.join().expect("reader"),
            0,
            "reader saw a torn document"
        );
    }
}
