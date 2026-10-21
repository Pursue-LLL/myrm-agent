include!("command_registry_macro.in");

macro_rules! command_name_list {
    ($(($name:literal, $handler:path)),* $(,)?) => {
        &[$($name),*]
    };
}

const COMMANDS: &[&str] = tauri_command_registry!(command_name_list);

fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(COMMANDS)),
    )
    .expect("Tauri build configuration should be valid");
}
