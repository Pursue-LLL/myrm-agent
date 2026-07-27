use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use uuid::Uuid;

const SENSITIVE_TICKET_TTL: Duration = Duration::from_secs(30);
pub(super) const MAX_PENDING_SENSITIVE_TICKETS: usize = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SensitiveAction {
    MigrateDataDir,
    ExportLocalSqlite,
}

impl SensitiveAction {
    pub fn from_str(value: &str) -> Option<Self> {
        match value {
            "migrate_data_dir" => Some(Self::MigrateDataDir),
            "export_local_sqlite" => Some(Self::ExportLocalSqlite),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::MigrateDataDir => "migrate_data_dir",
            Self::ExportLocalSqlite => "export_local_sqlite",
        }
    }
}

#[derive(Debug, Clone)]
struct TicketEntry {
    action: SensitiveAction,
    expires_at: Instant,
}

#[derive(Debug, Default)]
pub(super) struct TicketStore {
    entries: HashMap<String, TicketEntry>,
}

impl TicketStore {
    pub(super) fn issue(&mut self, action: SensitiveAction) -> Result<String, String> {
        self.issue_with_ttl(action, SENSITIVE_TICKET_TTL)
    }

    pub(super) fn issue_with_ttl(
        &mut self,
        action: SensitiveAction,
        ttl: Duration,
    ) -> Result<String, String> {
        self.prune_expired();
        if self.entries.len() >= MAX_PENDING_SENSITIVE_TICKETS {
            return Err("Too many pending sensitive action tickets; please retry".to_string());
        }
        let ticket = Uuid::new_v4().to_string();
        let entry = TicketEntry {
            action,
            expires_at: Instant::now() + ttl,
        };
        self.entries.insert(ticket.clone(), entry);
        Ok(ticket)
    }

    pub(super) fn consume(&mut self, action: SensitiveAction, ticket: &str) -> Result<(), String> {
        self.prune_expired();
        let entry = self.entries.remove(ticket).ok_or_else(|| {
            "Sensitive action ticket is missing, expired, or already used".to_string()
        })?;

        if entry.action != action {
            return Err(format!(
                "Sensitive action ticket mismatch: expected {}, got {}",
                action.as_str(),
                entry.action.as_str()
            ));
        }

        Ok(())
    }

    fn prune_expired(&mut self) {
        let now = Instant::now();
        self.entries.retain(|_, entry| entry.expires_at > now);
    }
}

static TICKETS: OnceLock<Mutex<TicketStore>> = OnceLock::new();

fn ticket_store() -> &'static Mutex<TicketStore> {
    TICKETS.get_or_init(|| Mutex::new(TicketStore::default()))
}

pub fn issue_sensitive_ticket(action: SensitiveAction) -> Result<String, String> {
    let mut store = ticket_store()
        .lock()
        .map_err(|_| "Failed to lock sensitive ticket store".to_string())?;
    store.issue(action)
}

pub fn consume_sensitive_ticket(action: SensitiveAction, ticket: &str) -> Result<(), String> {
    let mut store = ticket_store()
        .lock()
        .map_err(|_| "Failed to lock sensitive ticket store".to_string())?;
    store.consume(action, ticket)
}
