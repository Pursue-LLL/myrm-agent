//! 数据目录迁移核心引擎
//!
//! 提供数据目录迁移的前置校验、容量预检、动态条目扫描、文件复制与异常回滚能力。

use std::path::Path;

/// 检查某个文件名是否需要随数据目录一起迁移
#[must_use]
pub fn should_migrate_entry(file_name: &str) -> bool {
    let ignored_exact = [
        ".myrm_write_test",
        ".DS_Store",
        "Thumbs.db",
        "backend.pid",
        "desktop.lock",
    ];
    if ignored_exact.contains(&file_name) {
        return false;
    }
    if file_name.ends_with(".sock") || file_name.ends_with(".lock") || file_name.starts_with(".tmp")
    {
        return false;
    }
    true
}

/// 校验迁移目标路径的合法性、防嵌套保护以及写权限
pub fn validate_target_directory(old_path: &Path, new_path: &Path) -> Result<(), String> {
    if !new_path.exists() {
        std::fs::create_dir_all(new_path)
            .map_err(|e| format!("Failed to create target directory: {}", e))?;
    }

    if !new_path.is_dir() {
        return Err("Target path is not a directory".to_string());
    }

    let canonical_old = old_path
        .canonicalize()
        .unwrap_or_else(|_| old_path.to_path_buf());
    let canonical_new = new_path
        .canonicalize()
        .unwrap_or_else(|_| new_path.to_path_buf());

    if canonical_old == canonical_new {
        return Err("Target directory is identical to current data directory".to_string());
    }

    if canonical_new.starts_with(&canonical_old) {
        return Err("Target directory cannot be inside the current data directory".to_string());
    }

    let sensitive_conflict_files = ["data.db", "checkpoints.db", "tasks.db"];
    for file_name in &sensitive_conflict_files {
        if new_path.join(file_name).exists() {
            return Err(format!(
                "Target directory already contains existing data file ({}). Please choose an empty directory.",
                file_name
            ));
        }
    }

    let test_file = new_path.join(".myrm_write_test");
    std::fs::write(&test_file, b"test")
        .map_err(|_| "Target directory is not writable".to_string())?;
    let _ = std::fs::remove_file(&test_file);

    Ok(())
}

/// 递归计算目录下待迁移有效条目的总字节大小
#[must_use]
pub fn calculate_dir_size(path: &Path) -> u64 {
    if !path.exists() {
        return 0;
    }
    if path.is_file() {
        return std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    }
    let mut total_size: u64 = 0;
    if let Ok(entries) = std::fs::read_dir(path) {
        for entry in entries.flatten() {
            let file_name = entry.file_name().to_string_lossy().to_string();
            if should_migrate_entry(&file_name) {
                let entry_path = entry.path();
                if entry_path.is_dir() {
                    total_size = total_size.saturating_add(calculate_dir_size(&entry_path));
                } else if let Ok(meta) = entry.metadata() {
                    total_size = total_size.saturating_add(meta.len());
                }
            }
        }
    }
    total_size
}

/// 获取指定路径所在分区的可用磁盘空间（字节）
#[must_use]
#[cfg(unix)]
pub fn get_available_disk_space(path: &Path) -> Option<u64> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;

    let c_path = CString::new(path.as_os_str().as_bytes()).ok()?;
    let mut stat: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statvfs(c_path.as_ptr(), &mut stat) } == 0 {
        Some((stat.f_bavail as u64).saturating_mul(stat.f_frsize as u64))
    } else {
        None
    }
}

/// 获取指定路径所在分区的可用磁盘空间（字节）
#[must_use]
#[cfg(windows)]
pub fn get_available_disk_space(path: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;

    let wide_path: Vec<u16> = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let mut free_bytes_available: u64 = 0;
    let mut total_number_of_bytes: u64 = 0;
    let mut total_number_of_free_bytes: u64 = 0;

    extern "system" {
        fn GetDiskFreeSpaceExW(
            lpDirectoryName: *const u16,
            lpFreeBytesAvailableToCaller: *mut u64,
            lpTotalNumberOfBytes: *mut u64,
            lpTotalNumberOfFreeBytes: *mut u64,
        ) -> i32;
    }

    let res = unsafe {
        GetDiskFreeSpaceExW(
            wide_path.as_ptr(),
            &mut free_bytes_available,
            &mut total_number_of_bytes,
            &mut total_number_of_free_bytes,
        )
    };
    if res != 0 {
        Some(free_bytes_available)
    } else {
        None
    }
}

/// 非 Unix/Windows 平台的降级实现
#[must_use]
#[cfg(not(any(unix, windows)))]
pub fn get_available_disk_space(_path: &Path) -> Option<u64> {
    None
}

/// 递归复制目录
pub fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dst).map_err(|e| format!("Failed to create dir {:?}: {}", dst, e))?;
    for entry in
        std::fs::read_dir(src).map_err(|e| format!("Failed to read dir {:?}: {}", src, e))?
    {
        let entry = entry.map_err(|e| format!("Dir entry error: {}", e))?;
        let src_path = entry.path();
        let file_name = entry.file_name();
        let file_name_str = file_name.to_string_lossy();
        if !should_migrate_entry(&file_name_str) {
            continue;
        }
        let dst_path = dst.join(file_name);
        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            std::fs::copy(&src_path, &dst_path)
                .map_err(|e| format!("Failed to copy {:?}: {}", src_path, e))?;
        }
    }
    Ok(())
}

/// 清理迁移失败时在目标目录中已复制的顶层条目
pub fn cleanup_migrated_entries(dst_dir: &Path, copied_entries: &[String]) {
    for entry_name in copied_entries {
        let entry_path = dst_dir.join(entry_name);
        if entry_path.is_dir() {
            let _ = std::fs::remove_dir_all(&entry_path);
        } else if entry_path.is_file() {
            let _ = std::fs::remove_file(&entry_path);
        }
    }
}

/// 执行动态全量数据迁移，返回已复制的条目清单
pub fn perform_data_migration(old_path: &Path, new_path: &Path) -> Result<Vec<String>, String> {
    let mut copied_entries: Vec<String> = Vec::new();
    if !old_path.exists() {
        return Ok(copied_entries);
    }

    let read_res = std::fs::read_dir(old_path)
        .map_err(|e| format!("Failed to read source directory {:?}: {}", old_path, e))?;

    for entry in read_res {
        let entry = entry.map_err(|e| format!("Read entry error: {}", e))?;
        let file_name = entry.file_name().to_string_lossy().to_string();
        if !should_migrate_entry(&file_name) {
            continue;
        }

        let src = entry.path();
        let dst = new_path.join(&file_name);

        let copy_step = if src.is_dir() {
            copy_dir_recursive(&src, &dst)
        } else {
            if let Some(parent) = dst.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            std::fs::copy(&src, &dst)
                .map(|_| ())
                .map_err(|e| format!("Failed to copy file {}: {}", file_name, e))
        };

        if let Err(err) = copy_step {
            cleanup_migrated_entries(new_path, &copied_entries);
            return Err(err);
        }

        copied_entries.push(file_name);
    }

    Ok(copied_entries)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_should_migrate_entry() {
        assert!(should_migrate_entry("data.db"));
        assert!(should_migrate_entry("data.db-wal"));
        assert!(should_migrate_entry("data.db-shm"));
        assert!(should_migrate_entry("checkpoints.db"));
        assert!(should_migrate_entry("tasks.db"));
        assert!(should_migrate_entry("config_version"));
        assert!(should_migrate_entry("config_snapshot.json"));
        assert!(should_migrate_entry("skills"));
        assert!(should_migrate_entry("blobs"));
        assert!(should_migrate_entry("memory"));
        assert!(should_migrate_entry("qdrant"));

        assert!(!should_migrate_entry(".myrm_write_test"));
        assert!(!should_migrate_entry(".DS_Store"));
        assert!(!should_migrate_entry("Thumbs.db"));
        assert!(!should_migrate_entry("backend.pid"));
        assert!(!should_migrate_entry("desktop.lock"));
        assert!(!should_migrate_entry("server.sock"));
        assert!(!should_migrate_entry("session.lock"));
        assert!(!should_migrate_entry(".tmp_file"));
    }

    #[test]
    fn test_validate_target_directory_prevents_nesting() {
        let parent_tmp = tempdir().unwrap();
        let old_dir = parent_tmp.path().join("myrm_old");
        std::fs::create_dir_all(&old_dir).unwrap();
        let nested_new_dir = old_dir.join("sub_dir");

        let res = validate_target_directory(&old_dir, &nested_new_dir);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("cannot be inside"));
    }

    #[test]
    fn test_validate_target_directory_prevents_conflict() {
        let parent_tmp = tempdir().unwrap();
        let old_dir = parent_tmp.path().join("myrm_old");
        let new_dir = parent_tmp.path().join("myrm_new");
        std::fs::create_dir_all(&old_dir).unwrap();
        std::fs::create_dir_all(&new_dir).unwrap();

        std::fs::write(new_dir.join("data.db"), b"existing data").unwrap();

        let res = validate_target_directory(&old_dir, &new_dir);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("already contains existing data file"));
    }

    #[test]
    fn test_migration_and_cleanup() {
        let parent_tmp = tempdir().unwrap();
        let old_dir = parent_tmp.path().join("source");
        let new_dir = parent_tmp.path().join("target");
        std::fs::create_dir_all(&old_dir).unwrap();

        std::fs::write(old_dir.join("data.db"), b"main database").unwrap();
        std::fs::write(old_dir.join("tasks.db"), b"tasks database").unwrap();
        std::fs::write(old_dir.join(".DS_Store"), b"junk").unwrap();

        let skills_dir = old_dir.join("skills");
        std::fs::create_dir_all(&skills_dir).unwrap();
        std::fs::write(skills_dir.join("test_skill.py"), b"print(1)").unwrap();

        let copied = perform_data_migration(&old_dir, &new_dir).unwrap();
        assert!(copied.contains(&"data.db".to_string()));
        assert!(copied.contains(&"tasks.db".to_string()));
        assert!(copied.contains(&"skills".to_string()));
        assert!(!copied.contains(&".DS_Store".to_string()));

        assert!(new_dir.join("data.db").exists());
        assert!(new_dir.join("skills/test_skill.py").exists());
        assert!(!new_dir.join(".DS_Store").exists());

        cleanup_migrated_entries(&new_dir, &copied);
        assert!(!new_dir.join("data.db").exists());
        assert!(!new_dir.join("skills").exists());
    }
}
