use chrono::{DateTime, Utc};
use std::collections::VecDeque;
use std::path::PathBuf;

use crate::backend::{Backend, BackendError};

#[derive(Clone, Copy, PartialEq)]
pub enum Screen {
    Home,
    Chat,
}

#[derive(Clone)]
pub struct Message {
    pub role: Role,
    pub content: String,
    pub timestamp: DateTime<Utc>,
}

#[derive(Clone, Copy, PartialEq)]
pub enum Role {
    User,
    Assistant,
    System,
}

#[derive(Default)]
pub struct TokenStats {
    pub session_total: u64,
    pub last_input: u64,
    pub last_output: u64,
    pub cost_usd: f64,
    pub budget: Option<u64>,
}

impl TokenStats {
    pub fn budget_percentage(&self) -> Option<f64> {
        self.budget.map(|b| {
            if b == 0 {
                0.0
            } else {
                (self.session_total as f64 / b as f64) * 100.0
            }
        })
    }
}

// RAG status
#[derive(Default)]
pub struct RagStatus {
    pub initialized: bool,
    pub chunk_count: usize,
}

// Available commands for the popup
pub const COMMANDS: &[(&str, &str)] = &[
    ("/help", "Show available commands"),
    ("/clear", "Clear chat history"),
    ("/init", "Index current codebase"),
    ("/rag", "Show RAG status"),
    ("/search", "Search codebase (RAG)"),
    ("/session", "Session info"),
    ("/budget", "Token budget info"),
    ("/quit", "Exit OpenAgent"),
];

pub struct App {
    pub screen: Screen,
    pub messages: VecDeque<Message>,
    pub input: String,
    pub tokens: TokenStats,
    pub rag: RagStatus,
    pub cwd: PathBuf,
    pub scroll_offset: usize,
    pub is_loading: bool,
    pub animation_frame: usize,
    pub animation_tick: u64,
    pub backend: Backend,
    pub backend_connected: bool,
    pub status_message: Option<String>,
    // Command popup state
    pub command_selection: Option<usize>,  // None = original input, Some(n) = nth filtered command
}

impl App {
    pub fn new() -> Self {
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

        Self {
            screen: Screen::Home,
            messages: VecDeque::new(),
            input: String::new(),
            tokens: TokenStats::default(),
            rag: RagStatus::default(),
            cwd,
            scroll_offset: 0,
            is_loading: false,
            animation_frame: 0,
            animation_tick: 0,
            backend: Backend::new(),
            backend_connected: false,
            status_message: None,
            command_selection: None,
        }
    }

    /// Get the directory name (last component of cwd)
    pub fn cwd_name(&self) -> &str {
        self.cwd
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
    }

    /// Refresh RAG status from backend
    pub fn refresh_rag_status(&mut self) {
        if self.backend_connected {
            if let Ok(status) = self.backend.rag_status() {
                self.rag.initialized = status.initialized;
                self.rag.chunk_count = status.count;
            }
        }
    }

    /// Check if command popup should be shown
    pub fn showing_command_popup(&self) -> bool {
        self.input.starts_with('/') && !self.input.contains(' ')
    }

    /// Get filtered commands based on current input
    pub fn get_filtered_commands(&self) -> Vec<(&'static str, &'static str)> {
        if !self.input.starts_with('/') {
            return vec![];
        }
        let filter = &self.input[1..];
        COMMANDS
            .iter()
            .filter(|(cmd, _)| cmd[1..].starts_with(filter))
            .copied()
            .collect()
    }

    /// Move selection up in command popup
    pub fn command_select_up(&mut self) {
        let filtered = self.get_filtered_commands();
        if filtered.is_empty() {
            return;
        }

        // Cycle: None -> last command -> ... -> 0 -> None
        self.command_selection = match self.command_selection {
            None => Some(filtered.len() - 1),
            Some(0) => None,
            Some(n) => Some(n - 1),
        };
    }

    /// Move selection down in command popup
    pub fn command_select_down(&mut self) {
        let filtered = self.get_filtered_commands();
        if filtered.is_empty() {
            return;
        }

        // Cycle: None -> 0 -> 1 -> ... -> last -> None
        self.command_selection = match self.command_selection {
            None => Some(0),
            Some(n) if n >= filtered.len() - 1 => None,
            Some(n) => Some(n + 1),
        };
    }

    /// Apply selected command to input
    pub fn apply_command_selection(&mut self) {
        if let Some(idx) = self.command_selection {
            let filtered = self.get_filtered_commands();
            if let Some((cmd, _)) = filtered.get(idx) {
                self.input = cmd.to_string();
            }
        }
        self.command_selection = None;
    }

    /// Reset command selection when input changes
    pub fn reset_command_selection(&mut self) {
        self.command_selection = None;
    }

    pub fn start_backend(&mut self) -> Result<(), BackendError> {
        self.backend.start(None)?;
        self.backend_connected = true;

        // Create initial session with cwd as codebase path
        let cwd_str = self.cwd.to_string_lossy().to_string();
        let cwd_name = self.cwd_name().to_string();
        match self.backend.create_session(Some(&cwd_name), Some(&cwd_str)) {
            Ok(_session) => {
                self.status_message = Some(format!("Connected: {}", cwd_name));
            }
            Err(e) => {
                self.status_message = Some(format!("Session error: {}", e));
            }
        }

        // Get initial RAG status
        self.refresh_rag_status();

        Ok(())
    }

    pub fn tick(&mut self) {
        self.animation_tick += 1;
        // Update animation frame every tick for smooth 60fps animation
        // Using larger modulo (360) for smoother color transitions
        self.animation_frame = (self.animation_frame + 1) % 360;

        // Clear status message after ~3 seconds (180 ticks at 16ms)
        if self.animation_tick % 180 == 0 {
            self.status_message = None;
        }
    }

    pub fn submit_message(&mut self) {
        if self.input.trim().is_empty() {
            return;
        }

        // Handle slash commands locally
        if self.input.starts_with('/') {
            self.handle_command();
            return;
        }

        let user_msg = Message {
            role: Role::User,
            content: self.input.clone(),
            timestamp: Utc::now(),
        };
        self.messages.push_back(user_msg);
        let user_input = self.input.clone();
        self.input.clear();
        self.is_loading = true;

        // Try to get response from backend
        if self.backend_connected {
            match self.backend.chat_send(&user_input) {
                Ok(response) => {
                    let assistant_msg = Message {
                        role: Role::Assistant,
                        content: response.response,
                        timestamp: Utc::now(),
                    };
                    self.messages.push_back(assistant_msg);

                    // Update token stats from response
                    if let Some(tokens) = response.tokens {
                        self.tokens.session_total = tokens.total_tokens;
                        self.tokens.last_input = tokens.total_input;
                        self.tokens.last_output = tokens.total_output;
                        self.tokens.cost_usd = tokens.total_cost;
                        self.tokens.budget = tokens.budget;
                    }
                }
                Err(e) => {
                    let error_msg = Message {
                        role: Role::System,
                        content: format!("Error: {}", e),
                        timestamp: Utc::now(),
                    };
                    self.messages.push_back(error_msg);
                }
            }
        } else {
            // Fallback mock response when not connected
            let assistant_msg = Message {
                role: Role::Assistant,
                content: "Backend not connected. Run with Python backend for full functionality.".to_string(),
                timestamp: Utc::now(),
            };
            self.messages.push_back(assistant_msg);

            // Update mock token stats
            self.tokens.session_total += 150;
            self.tokens.last_input = 50;
            self.tokens.last_output = 100;
            self.tokens.cost_usd += 0.001;
        }

        self.is_loading = false;
        self.scroll_offset = 0;
    }

    /// Handle slash commands locally
    fn handle_command(&mut self) {
        let cmd = self.input.trim();
        let (command, args) = cmd.split_once(' ').unwrap_or((cmd, ""));
        let args = args.trim();

        let response = match command {
            "/help" => {
                let mut help_text = String::from("Available commands:\n");
                for (cmd, desc) in COMMANDS {
                    help_text.push_str(&format!("  {} - {}\n", cmd, desc));
                }
                help_text
            }
            "/clear" => {
                self.messages.clear();
                self.input.clear();
                self.status_message = Some("Chat cleared".to_string());
                return;
            }
            "/init" => {
                if !self.backend_connected {
                    "Error: Backend not connected".to_string()
                } else {
                    // Use current cwd, optionally clear existing
                    let clear = args == "--clear" || args == "-c";
                    let cwd_str = self.cwd.to_string_lossy().to_string();

                    self.status_message = Some("Indexing codebase...".to_string());

                    match self.backend.codebase_init(Some(&cwd_str), clear) {
                        Ok(response) => {
                            if let Some(err) = response.error {
                                format!("Init error: {}", err)
                            } else {
                                self.refresh_rag_status();
                                let mut output = format!(
                                    "Codebase indexed!\n  Chunks: {}\n",
                                    response.chunks
                                );
                                if let Some(stats) = response.stats {
                                    output.push_str(&format!(
                                        "  Files scanned: {}\n  Code units: {}\n",
                                        stats.files_scanned,
                                        stats.units_extracted
                                    ));
                                }
                                if let Some(msg) = response.message {
                                    output.push_str(&format!("  {}", msg));
                                }
                                output
                            }
                        }
                        Err(e) => format!("Init failed: {}", e),
                    }
                }
            }
            "/rag" => {
                self.refresh_rag_status();
                if self.rag.initialized {
                    format!(
                        "RAG Status:\n  Initialized: Yes\n  Chunks indexed: {}\n  Ready for queries",
                        self.rag.chunk_count
                    )
                } else {
                    "RAG Status:\n  Initialized: No\n  Use /init to index the codebase".to_string()
                }
            }
            "/search" => {
                if args.is_empty() {
                    "Usage: /search <query>\n  Example: /search authentication middleware".to_string()
                } else if !self.backend_connected {
                    "Error: Backend not connected".to_string()
                } else {
                    match self.backend.rag_search(args, Some(5)) {
                        Ok(response) => {
                            if let Some(err) = response.error {
                                format!("Search error: {}", err)
                            } else if response.results.is_empty() {
                                "No results found".to_string()
                            } else {
                                let mut output = format!("Found {} results:\n", response.count);
                                for (i, r) in response.results.iter().enumerate() {
                                    output.push_str(&format!(
                                        "\n{}. [{}] {}\n   {}\n   Relevance: {:.1}%",
                                        i + 1,
                                        r.metadata.chunk_type,
                                        r.metadata.path,
                                        r.content.chars().take(100).collect::<String>(),
                                        r.relevance * 100.0
                                    ));
                                }
                                output
                            }
                        }
                        Err(e) => format!("Search failed: {}", e),
                    }
                }
            }
            "/ingest" => {
                if args.is_empty() {
                    "Usage: /ingest <json_path>\n  Example: /ingest ./specs/codebase.json".to_string()
                } else if !self.backend_connected {
                    "Error: Backend not connected".to_string()
                } else {
                    match self.backend.rag_ingest_json(args) {
                        Ok(response) => {
                            if let Some(err) = response.error {
                                format!("Ingest error: {}", err)
                            } else {
                                self.refresh_rag_status();
                                format!(
                                    "Ingested {} chunks from {}\nTotal chunks: {}",
                                    response.ingested,
                                    response.source.unwrap_or_default(),
                                    self.rag.chunk_count
                                )
                            }
                        }
                        Err(e) => format!("Ingest failed: {}", e),
                    }
                }
            }
            "/session" => {
                format!(
                    "Session info:\n  Project: {}\n  Path: {}\n  Messages: {}\n  Tokens: {}\n  Cost: ${:.4}\n  Status: {}\n  RAG: {} chunks",
                    self.cwd_name(),
                    self.cwd.display(),
                    self.messages.len(),
                    self.tokens.session_total,
                    self.tokens.cost_usd,
                    if self.backend_connected { "Connected" } else { "Offline" },
                    self.rag.chunk_count
                )
            }
            "/budget" => {
                if let Some(budget) = self.tokens.budget {
                    format!(
                        "Token budget: {}\n  Used: {} ({:.1}%)\n  Remaining: {}",
                        budget,
                        self.tokens.session_total,
                        self.tokens.budget_percentage().unwrap_or(0.0),
                        budget.saturating_sub(self.tokens.session_total)
                    )
                } else {
                    "No budget set. Use /budget <tokens> to set one.".to_string()
                }
            }
            "/quit" => {
                self.input.clear();
                self.status_message = Some("Use ESC or Ctrl+C to quit".to_string());
                return;
            }
            _ => {
                format!("Unknown command: {}. Type /help for available commands.", command)
            }
        };

        let system_msg = Message {
            role: Role::System,
            content: response,
            timestamp: Utc::now(),
        };
        self.messages.push_back(system_msg);
        self.input.clear();
        self.scroll_offset = 0;
    }

    pub fn scroll_up(&mut self) {
        if self.scroll_offset < self.messages.len().saturating_sub(1) {
            self.scroll_offset += 1;
        }
    }

    pub fn scroll_down(&mut self) {
        if self.scroll_offset > 0 {
            self.scroll_offset -= 1;
        }
    }
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}
