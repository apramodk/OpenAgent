/// Application configuration and constants.

pub struct Config {
    /// Main loop tick rate in milliseconds (target 60 FPS = ~16ms)
    pub tick_rate_ms: u64,
    
    /// How many ticks to show status messages (180 = ~3s at 60fps)
    pub status_timeout_ticks: u64,
    
    /// Modulo for animation frame counter
    pub animation_frame_mod: usize,
    
    /// Interval for writing debug dumps
    pub debug_dump_interval_ticks: u64,
    
    /// Interval for auto-hiding activity log
    pub activity_log_autohide_ticks: u64,
    
    /// Duration of send animation in ticks
    pub send_animation_ticks: u8,
    
    /// Lines to scroll per key press
    pub scroll_step: usize,
    
    /// Estimated lines per message for scroll buffer calculation
    pub scroll_lines_per_message: usize,
    
    /// Minimum scroll buffer size in lines
    pub scroll_min_buffer: usize,
    
    /// Width of the sidebar in characters
    pub sidebar_width: u16,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            tick_rate_ms: 16,
            status_timeout_ticks: 180,
            animation_frame_mod: 360,
            debug_dump_interval_ticks: 30,
            activity_log_autohide_ticks: 120,
            send_animation_ticks: 20,
            scroll_step: 3,
            scroll_lines_per_message: 50,
            scroll_min_buffer: 1000,
            sidebar_width: 26,
        }
    }
}

/// Global commands list
pub const COMMANDS: &[(&str, &str)] = &[
    ("/help", "Show available commands"),
    ("/clear", "Clear chat history"),
    ("/init", "Index current codebase"),
    ("/rag", "Show RAG status"),
    ("/search", "Search codebase (RAG)"),
    ("/model", "Get/set LLM model"),
    ("/session", "Session info"),
    ("/budget", "Token budget info"),
    ("/debug", "Toggle debug overlay"),
    ("/copy", "Export chat to file"),
    ("/quit", "Exit OpenAgent"),
];

/// Features coming soon
pub const COMING_SOON: &[&str] = &[
    "Streaming responses",
    "Tool execution",
    "Intent routing (DSPy)",
    "Cancel requests",
    "Multi-session",
];
