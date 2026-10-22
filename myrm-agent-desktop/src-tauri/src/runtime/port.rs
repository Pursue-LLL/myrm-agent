//! 端口占用检测
//!
//! [INPUT]
//! - std::net::{TcpListener, TcpStream} (POS: 端口连通性探测)
//!
//! [OUTPUT]
//! - is_port_in_use: 端口是否已被任何地址族上的监听者占用
//!
//! [POS]
//! 只回答「这个端口现在能不能用」：既做 bind 探测，也做 connect 探测。
//! connect 探测是必须的——只看 bind 会漏掉绑定在另一地址族（例如 IPv6 `*:3000`）上的监听者，
//! 桌面端会因此误以为端口空闲，随后自己的子进程启动失败。

use std::net::{Ipv4Addr, Ipv6Addr, SocketAddr, TcpListener, TcpStream};
use std::time::Duration;

pub(crate) fn is_port_in_use(host: &str, port: u16) -> bool {
    if TcpListener::bind((host, port)).is_err() {
        return true;
    }
    // 另一地址族上的监听者（常见：开发栈用 IPv6 `*:port`）不会阻止本机 IPv4 bind，
    // 但子进程仍会 EADDRINUSE 退出，所以必须显式探测。
    for addr in [
        SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
        SocketAddr::from((Ipv6Addr::LOCALHOST, port)),
    ] {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok() {
            return true;
        }
    }
    false
}
