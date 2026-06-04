//! 端口占用检测

use std::net::TcpListener;

pub(crate) fn is_port_in_use(host: &str, port: u16) -> bool {
    TcpListener::bind((host, port)).is_err()
}
