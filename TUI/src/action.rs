/// User actions that can be triggered by commands or UI events.
#[derive(Debug, Clone, PartialEq)]
pub enum Action {
    /// Show help message
    Help,
    /// Clear chat history
    ClearHistory,
    /// Initialize codebase indexing
    InitCodebase {
        clear: bool,
    },
    /// Show RAG status
    ShowRagStatus,
    /// Search RAG
    Search {
        query: String,
    },
    /// Ingest JSON data
    Ingest {
        path: String,
    },
    /// Show session info
    ShowSessionInfo,
    /// Get or set model
    Model {
        id: Option<String>,
    },
    /// Show budget info
    ShowBudget,
    /// Toggle debug mode
    ToggleDebug,
    /// Export chat
    ExportChat,
    /// Quit application
    Quit,
    /// Generic system message (fallback)
    SystemMessage(String),
}
