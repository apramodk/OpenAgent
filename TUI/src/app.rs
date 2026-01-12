use chrono::{DateTime, Utc};
use serde::Serialize;
use std::collections::VecDeque;
use std::fs;
use std::path::PathBuf;
use std::sync::mpsc::Receiver;

use crate::backend::{Backend, BackendError, StreamEvent, EmbeddingPoint};
use crate::config::{Config, COMMANDS};
use crate::action::Action;
use crate::command::CommandParser;
use crate::ui_state::{UIState, Screen, Focus};

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

// Activity log entry
#[derive(Clone)]
pub struct Activity {
    pub message: String,
    pub timestamp: DateTime<Utc>,
    pub is_complete: bool,
}

impl Activity {
    pub fn new(message: &str) -> Self {
        Self {
            message: message.to_string(),
            timestamp: Utc::now(),
            is_complete: false,
        }
    }

    pub fn complete(&mut self) {
        self.is_complete = true;
    }
}

// Activity log for showing what's happening
pub struct ActivityLog {
    pub entries: VecDeque<Activity>,
    pub max_entries: usize,
    pub visible: bool,
}

impl Default for ActivityLog {
    fn default() -> Self {
        Self {
            entries: VecDeque::new(),
            max_entries: 8,
            visible: false,
        }
    }
}

impl ActivityLog {
    pub fn push(&mut self, message: &str) {
        self.entries.push_back(Activity::new(message));
        while self.entries.len() > self.max_entries {
            self.entries.pop_front();
        }
        self.visible = true;
    }

    pub fn complete_last(&mut self) {
        if let Some(last) = self.entries.back_mut() {
            last.complete();
        }
    }

    pub fn clear(&mut self) {
        self.entries.clear();
        self.visible = false;
    }

    pub fn hide(&mut self) {
        self.visible = false;
    }

    pub fn has_pending(&self) -> bool {
        self.entries.iter().any(|a| !a.is_complete)
    }
}

/// Debug dump structure for external analysis
#[derive(Serialize)]
pub struct DebugDump {
    pub timestamp: String,
    pub cwd: String,
    pub screen: String,
    pub backend_connected: bool,
    pub debug_mode: bool,
    pub messages: Vec<DebugMessage>,
    pub tokens: DebugTokens,
    pub rag: DebugRag,
    pub input_buffer: String,
}

#[derive(Serialize)]
pub struct DebugMessage {
    pub role: String,
    pub content: String,
    pub timestamp: String,
}

#[derive(Serialize)]
pub struct DebugTokens {
    pub session_total: u64,
    pub last_input: u64,
    pub last_output: u64,
    pub cost_usd: f64,
    pub budget: Option<u64>,
}

#[derive(Serialize)]
pub struct DebugRag {
    pub initialized: bool,
    pub chunk_count: usize,
}

pub struct App {
    pub config: Config,
    pub ui: UIState,
    pub messages: VecDeque<Message>,
    pub tokens: TokenStats,
    pub rag: RagStatus,
    pub cwd: PathBuf,
    pub animation_frame: usize,
    pub animation_tick: u64,
    pub backend: Backend,
    pub backend_connected: bool,
    // Activity log - shows what's happening
    pub activity: ActivityLog,
    // Streaming state
    stream_receiver: Option<Receiver<StreamEvent>>,
    streaming_content: String,
    pub embedding_points: Vec<EmbeddingPoint>,
}

impl App {
    pub fn new() -> Self {
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

        Self {
            config: Config::default(),
            ui: UIState::new(),
            messages: VecDeque::new(),
            tokens: TokenStats::default(),
            rag: RagStatus::default(),
            cwd,
            animation_frame: 0,
            animation_tick: 0,
            backend: Backend::new(),
            backend_connected: false,
            activity: ActivityLog::default(),
            stream_receiver: None,
            streaming_content: String::new(),
            embedding_points: Vec::new(),
        }
    }

    /// Create a debug dump of current state
    pub fn create_debug_dump(&self) -> DebugDump {
        DebugDump {
            timestamp: Utc::now().to_rfc3339(),
            cwd: self.cwd.to_string_lossy().to_string(),
            screen: match self.ui.screen {
                Screen::Home => "Home".to_string(),
                Screen::Chat => "Chat".to_string(),
            },
            backend_connected: self.backend_connected,
            debug_mode: self.ui.debug_mode,
            messages: self.messages.iter().map(|m| DebugMessage {
                role: match m.role {
                    Role::User => "user".to_string(),
                    Role::Assistant => "assistant".to_string(),
                    Role::System => "system".to_string(),
                },
                content: m.content.clone(),
                timestamp: m.timestamp.to_rfc3339(),
            }).collect(),
            tokens: DebugTokens {
                session_total: self.tokens.session_total,
                last_input: self.tokens.last_input,
                last_output: self.tokens.last_output,
                cost_usd: self.tokens.cost_usd,
                budget: self.tokens.budget,
            },
            rag: DebugRag {
                initialized: self.rag.initialized,
                chunk_count: self.rag.chunk_count,
            },
            input_buffer: self.ui.input.clone(),
        }
    }

    /// Write debug dump to file (called on each tick when debug_mode is on)
    pub fn write_debug_dump(&self) {
        if !self.ui.debug_mode {
            return;
        }
        let dump = self.create_debug_dump();
        let debug_path = self.cwd.join(".openagent-debug.json");
        if let Ok(json) = serde_json::to_string_pretty(&dump) {
            let _ = fs::write(&debug_path, json);
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

    /// Refresh token stats from backend
    pub fn refresh_token_stats(&mut self) {
        if self.backend_connected {
            if let Ok(stats) = self.backend.get_token_stats() {
                self.tokens.session_total = stats.total_tokens;
                self.tokens.last_input = stats.total_input;
                self.tokens.last_output = stats.total_output;
                self.tokens.cost_usd = stats.total_cost;
                self.tokens.budget = stats.budget;
            }
        }
    }

    /// Check if command popup should be shown
    pub fn showing_command_popup(&self) -> bool {
        self.ui.input.starts_with('/') && !self.ui.input.contains(' ')
    }

    /// Get filtered commands based on current input
    pub fn get_filtered_commands(&self) -> Vec<(&'static str, &'static str)> {
        if !self.ui.input.starts_with('/') {
            return vec![];
        }
        let filter = &self.ui.input[1..];
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
        self.ui.command_selection = match self.ui.command_selection {
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
        self.ui.command_selection = match self.ui.command_selection {
            None => Some(0),
            Some(n) if n >= filtered.len() - 1 => None,
            Some(n) => Some(n + 1),
        };
    }

    /// Apply selected command to input
    pub fn apply_command_selection(&mut self) {
        if let Some(idx) = self.ui.command_selection {
            let filtered = self.get_filtered_commands();
            if let Some((cmd, _)) = filtered.get(idx) {
                self.ui.input = cmd.to_string();
            }
        }
        self.ui.command_selection = None;
    }

    /// Reset command selection when input changes
    pub fn reset_command_selection(&mut self) {
        self.ui.command_selection = None;
    }

    pub fn start_backend(&mut self) -> Result<(), BackendError> {
        self.backend.start(None)?;
        self.backend_connected = true;

        // Create initial session with cwd as codebase path
        let cwd_str = self.cwd.to_string_lossy().to_string();
        let cwd_name = self.cwd_name().to_string();
        match self.backend.create_session(Some(&cwd_name), Some(&cwd_str)) {
            Ok(_session) => {
                self.ui.status_message = Some(format!("Connected: {}", cwd_name));
            }
            Err(e) => {
                self.ui.status_message = Some(format!("Session error: {}", e));
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
        self.animation_frame = (self.animation_frame + 1) % self.config.animation_frame_mod;

        // Clear status message after ~3 seconds (180 ticks at 16ms)
        if self.animation_tick % self.config.status_timeout_ticks == 0 {
            self.ui.status_message = None;
        }

        // Write debug dump every ~500ms when debug mode is enabled
        if self.ui.debug_mode && self.animation_tick % self.config.debug_dump_interval_ticks == 0 {
            self.write_debug_dump();
        }

        // Auto-hide activity log after ~2 seconds when no pending activities
        if self.activity.visible && !self.activity.has_pending() && !self.ui.is_loading {
            if self.animation_tick % self.config.activity_log_autohide_ticks == 0 {
                self.activity.hide();
            }
        }

        // Decrement send animation counter
        if self.ui.send_animation > 0 {
            self.ui.send_animation = self.ui.send_animation.saturating_sub(1);
        }

        // Poll for streaming updates
        self.poll_stream();
    }

    /// Poll for streaming updates and update the message content
    fn poll_stream(&mut self) {
        use std::sync::mpsc::TryRecvError;

        if self.stream_receiver.is_none() {
            return;
        }

        let receiver = self.stream_receiver.as_ref().unwrap();

        // Process all available chunks (non-blocking)
        loop {
            match receiver.try_recv() {
                Ok(StreamEvent::Chunk(chunk)) => {
                    self.streaming_content.push_str(&chunk);
                    // Update the last message with streamed content
                    if let Some(msg) = self.messages.back_mut() {
                        if msg.role == Role::Assistant {
                            msg.content = self.streaming_content.clone();
                        }
                    }
                }
                Ok(StreamEvent::Done { tokens }) => {
                    // Streaming complete
                    self.ui.is_loading = false;
                    self.stream_receiver = None;
                    self.streaming_content.clear();
                    self.backend.clear_stream();
                    self.activity.complete_last();

                    // Update token stats from the done notification (pushed, not fetched)
                    if let Some(stats) = tokens {
                        self.tokens.session_total = stats.total_tokens;
                        self.tokens.last_input = stats.total_input;
                        self.tokens.last_output = stats.total_output;
                        self.tokens.cost_usd = stats.total_cost;
                        self.tokens.budget = stats.budget;
                    }
                    break;
                }
                Err(TryRecvError::Empty) => {
                    // No more chunks available right now
                    break;
                }
                Err(TryRecvError::Disconnected) => {
                    // Stream ended unexpectedly
                    self.ui.is_loading = false;
                    self.stream_receiver = None;
                    self.streaming_content.clear();
                    self.backend.clear_stream();
                    self.activity.complete_last();
                    break;
                }
            }
        }
    }

    pub fn submit_message(&mut self) {
        if self.ui.input.trim().is_empty() {
            return;
        }

        // Handle slash commands locally
        if self.ui.input.starts_with('/') {
            self.handle_command();
            return;
        }

        let user_msg = Message {
            role: Role::User,
            content: self.ui.input.clone(),
            timestamp: Utc::now(),
        };
        self.messages.push_back(user_msg);
        let user_input = self.ui.input.clone();
        self.ui.input.clear();
        self.ui.is_loading = true;
        self.ui.send_animation = self.config.send_animation_ticks; // ~320ms animation at 60fps
        self.ui.scroll_offset = 0;   // Scroll to bottom on send

        // Show activity
        self.activity.clear();
        self.activity.push("Sending message to LLM...");

        // Try to get response from backend with streaming
        if self.backend_connected {
            // Add RAG activity if applicable
            if self.rag.initialized {
                self.activity.complete_last();
                self.activity.push("Searching codebase context...");
            }

            // Start streaming request
            match self.backend.chat_send_stream(&user_input) {
                Ok(receiver) => {
                    self.activity.complete_last();
                    self.activity.push("Streaming response...");

                    // Store the receiver and create placeholder message
                    self.stream_receiver = Some(receiver);
                    self.streaming_content = String::new();

                    // Add empty assistant message that will be filled by streaming
                    let assistant_msg = Message {
                        role: Role::Assistant,
                        content: String::new(),
                        timestamp: Utc::now(),
                    };
                    self.messages.push_back(assistant_msg);
                }
                Err(e) => {
                    self.activity.complete_last();
                    self.ui.is_loading = false;
                    let error_msg = Message {
                        role: Role::System,
                        content: format!("Error: {}", e),
                        timestamp: Utc::now(),
                    };
                    self.messages.push_back(error_msg);
                }
            }
        } else {
            self.activity.complete_last();
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

        self.ui.is_loading = false;
        self.ui.scroll_offset = 0;
    }

    fn add_system_message(&mut self, content: &str) {
        let system_msg = Message {
            role: Role::System,
            content: content.to_string(),
            timestamp: Utc::now(),
        };
        self.messages.push_back(system_msg);
    }

    /// Handle slash commands locally
    fn handle_command(&mut self) {
        match CommandParser::parse(&self.ui.input) {
            Ok(action) => self.process_action(action),
            Err(msg) => self.add_system_message(&msg),
        }
        self.ui.input.clear();
        self.ui.scroll_offset = 0;
    }

    /// Process a parsed action
    fn process_action(&mut self, action: Action) {
        match action {
            Action::Help => {
                let mut help_text = String::from("Available commands:\n");
                for (cmd, desc) in COMMANDS {
                    help_text.push_str(&format!("  {} - {}\n", cmd, desc));
                }
                self.add_system_message(&help_text);
            }
            Action::ClearHistory => {
                self.messages.clear();
                self.ui.status_message = Some("Chat cleared".to_string());
            }
            Action::InitCodebase { clear } => {
                if !self.backend_connected {
                    self.add_system_message("Error: Backend not connected");
                } else {
                    let cwd_str = self.cwd.to_string_lossy().to_string();
                    self.ui.status_message = Some("Indexing codebase...".to_string());
                    self.activity.clear();
                    self.activity.push("Scanning codebase...");

                    match self.backend.codebase_init(Some(&cwd_str), clear) {
                        Ok(response) => {
                            self.activity.complete_last();
                            if let Some(err) = response.error {
                                self.add_system_message(&format!("Init error: {}", err));
                            } else {
                                self.activity.push("Extracting code semantics...");
                                self.activity.complete_last();
                                self.activity.push("Building vector embeddings...");
                                self.activity.complete_last();

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
                                self.add_system_message(&output);
                            }
                        }
                        Err(e) => {
                            self.activity.complete_last();
                            self.add_system_message(&format!("Init failed: {}", e));
                        }
                    }
                }
            }
            Action::ShowRagStatus => {
                self.refresh_rag_status();
                if self.rag.initialized {
                    self.add_system_message(&format!(
                        "RAG Status:\n  Initialized: Yes\n  Chunks indexed: {}\n  Ready for queries",
                        self.rag.chunk_count
                    ));
                } else {
                    self.add_system_message("RAG Status:\n  Initialized: No\n  Use /init to index the codebase");
                }
            }
            Action::Search { query } => {
                if !self.backend_connected {
                    self.add_system_message("Error: Backend not connected");
                } else {
                    self.activity.clear();
                    self.activity.push("Searching codebase...");

                    match self.backend.rag_search(&query, Some(5)) {
                        Ok(response) => {
                            self.activity.complete_last();
                            if let Some(err) = response.error {
                                self.add_system_message(&format!("Search error: {}", err));
                            } else if response.results.is_empty() {
                                self.add_system_message("No results found");
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
                                self.add_system_message(&output);
                            }
                        }
                        Err(e) => {
                            self.activity.complete_last();
                            self.add_system_message(&format!("Search failed: {}", e));
                        }
                    }
                }
            }
            Action::Ingest { path } => {
                if !self.backend_connected {
                    self.add_system_message("Error: Backend not connected");
                } else {
                    match self.backend.rag_ingest_json(&path) {
                        Ok(response) => {
                            if let Some(err) = response.error {
                                self.add_system_message(&format!("Ingest error: {}", err));
                            } else {
                                self.refresh_rag_status();
                                self.add_system_message(&format!(
                                    "Ingested {} chunks from {}\nTotal chunks: {}",
                                    response.ingested,
                                    response.source.unwrap_or_default(),
                                    self.rag.chunk_count
                                ));
                            }
                        }
                        Err(e) => self.add_system_message(&format!("Ingest failed: {}", e)),
                    }
                }
            }
            Action::ShowSessionInfo => {
                self.add_system_message(&format!(
                    "Session info:\n  Project: {}\n  Path: {}\n  Messages: {}\n  Tokens: {}\n  Cost: ${:.4}\n  Status: {}\n  RAG: {} chunks",
                    self.cwd_name(),
                    self.cwd.display(),
                    self.messages.len(),
                    self.tokens.session_total,
                    self.tokens.cost_usd,
                    if self.backend_connected { "Connected" } else { "Offline" },
                    self.rag.chunk_count
                ));
            }
            Action::Model { id } => {
                if !self.backend_connected {
                    self.add_system_message("Error: Backend not connected");
                } else if let Some(model_id) = id {
                    // Set model
                    match self.backend.model_set(&model_id) {
                        Ok(resp) => {
                            if let Some(err) = resp.error {
                                self.add_system_message(&format!("Error: {}", err));
                            } else {
                                let new_model = resp.model.unwrap_or_else(|| model_id.clone());
                                let prev = resp.previous.unwrap_or_else(|| "unknown".to_string());
                                self.add_system_message(&format!("Model changed: {} -> {}", prev, new_model));
                            }
                        }
                        Err(e) => self.add_system_message(&format!("Failed to set model: {}", e)),
                    }
                } else {
                    // List models
                    let current = match self.backend.model_get() {
                        Ok(resp) => resp.model.unwrap_or_else(|| "unknown".to_string()),
                        Err(_) => "unknown".to_string(),
                    };

                    let mut output = format!("Current model: {}\n\nAvailable models:\n", current);

                    if let Ok(list) = self.backend.model_list() {
                        for m in list.models {
                            let marker = if m.id == current { " *" } else { "" };
                            output.push_str(&format!("  {} - {}{}\n", m.id, m.description, marker));
                        }
                    }
                    output.push_str("\nUsage: /model <model_id>");
                    self.add_system_message(&output);
                }
            }
            Action::ShowBudget => {
                if let Some(budget) = self.tokens.budget {
                    self.add_system_message(&format!(
                        "Token budget: {}\n  Used: {} ({:.1}%)\n  Remaining: {}",
                        budget,
                        self.tokens.session_total,
                        self.tokens.budget_percentage().unwrap_or(0.0),
                        budget.saturating_sub(self.tokens.session_total)
                    ));
                } else {
                    self.add_system_message("No budget set. Use /budget <tokens> to set one.");
                }
            }
            Action::ToggleDebug => {
                self.ui.debug_mode = !self.ui.debug_mode;
                if self.ui.debug_mode {
                    self.add_system_message("Debug overlay ENABLED\n  Press /debug again to close");
                } else {
                    self.add_system_message("Debug overlay DISABLED");
                }
            }
            Action::ExportChat => {
                // Export chat to a readable text file
                let export_path = self.cwd.join(".openagent-chat.txt");
                let mut content = String::new();
                content.push_str(&format!("# OpenAgent Chat Export\n"));
                content.push_str(&format!("# Project: {}\n", self.cwd_name()));
                content.push_str(&format!("# Exported: {}\n", Utc::now().format("%Y-%m-%d %H:%M:%S UTC")));
                content.push_str(&format!("# Messages: {}\n", self.messages.len()));
                content.push_str(&format!("# Tokens: {} (${:.4})\n", self.tokens.session_total, self.tokens.cost_usd));
                content.push_str("\n---\n\n");

                for msg in &self.messages {
                    let role = match msg.role {
                        Role::User => "USER",
                        Role::Assistant => "ASSISTANT",
                        Role::System => "SYSTEM",
                    };
                    content.push_str(&format!("[{}] {}\n", role, msg.timestamp.format("%H:%M:%S")));
                    content.push_str(&msg.content);
                    content.push_str("\n\n---\n\n");
                }

                match fs::write(&export_path, &content) {
                    Ok(_) => self.add_system_message(&format!(
                        "Chat exported to:\n  {}\n\n  {} messages, {} bytes\n  Ready to copy!",
                        export_path.display(),
                        self.messages.len(),
                        content.len()
                    )),
                    Err(e) => self.add_system_message(&format!("Export failed: {}", e)),
                }
            }
            Action::Quit => {
                self.ui.status_message = Some("Use ESC or Ctrl+C to quit".to_string());
            }
            Action::SystemMessage(msg) => {
                self.add_system_message(&msg);
            }
        }
    }

    pub fn scroll_up(&mut self) {
        // Scroll up - UI will clamp to actual max based on rendered line count
        // Use generous upper bound (~50 lines per message for long responses)
        // The UI's clamped_offset handles the real limit
        let max_offset = self.messages.len()
            .saturating_mul(self.config.scroll_lines_per_message)
            .max(self.config.scroll_min_buffer);
        if self.ui.scroll_offset < max_offset {
            self.ui.scroll_offset += self.config.scroll_step;
        }
    }

    pub fn scroll_down(&mut self) {
        // Scroll towards bottom (offset 0 = at bottom)
        self.ui.scroll_offset = self.ui.scroll_offset.saturating_sub(self.config.scroll_step);
    }

    /// Toggle visualization panel
    pub fn toggle_visualization(&mut self) {
        self.ui.show_visualization = !self.ui.show_visualization;
        if self.ui.show_visualization {
            self.load_embeddings();
            self.ui.focus = Focus::Visualization;
        } else {
            self.ui.focus = Focus::Input;
        }
    }

    /// Load embeddings from backend
    pub fn load_embeddings(&mut self) {
        if !self.backend_connected {
            self.ui.status_message = Some("Cannot load embeddings: backend not connected".to_string());
            return;
        }

        match self.backend.rag_embeddings() {
            Ok(response) => {
                if let Some(err) = response.error {
                    self.ui.status_message = Some(format!("Embeddings error: {}", err));
                    self.embedding_points.clear();
                } else if response.points.is_empty() {
                    self.ui.status_message = Some("No embeddings found. Use /init to index codebase.".to_string());
                    self.embedding_points.clear();
                } else {
                    self.ui.status_message = Some(format!("Loaded {} embeddings", response.points.len()));
                    self.embedding_points = response.points;
                }
            }
            Err(e) => {
                self.ui.status_message = Some(format!("Failed to load embeddings: {}", e));
                self.embedding_points.clear();
            }
        }
    }

    /// Cycle focus between panels
    pub fn cycle_focus(&mut self) {
        self.ui.focus = match self.ui.focus {
            Focus::Input => Focus::Chat,
            Focus::Chat => {
                if self.ui.show_visualization {
                    Focus::Visualization
                } else {
                    Focus::Input
                }
            }
            Focus::Visualization => Focus::Input,
        };
    }

    /// Find point at screen coordinates (returns point index)
    pub fn find_point_at(&self, x: f64, y: f64, tolerance: f64) -> Option<usize> {
        for (i, point) in self.embedding_points.iter().enumerate() {
            let dx = point.x - x;
            let dy = point.y - y;
            if (dx * dx + dy * dy).sqrt() < tolerance {
                return Some(i);
            }
        }
        None
    }

    /// Toggle between raw markdown and rendered preview
    pub fn toggle_markdown_mode(&mut self) {
        self.ui.show_raw_markdown = !self.ui.show_raw_markdown;
        self.ui.status_message = Some(
            if self.ui.show_raw_markdown {
                "Markdown: raw view".to_string()
            } else {
                "Markdown: rendered preview".to_string()
            }
        );
    }
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}
