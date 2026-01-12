#[derive(Clone, Copy, PartialEq, Default)]
pub enum Screen {
    #[default]
    Home,
    Chat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Focus {
    Chat,
    #[default]
    Input,
    Visualization,
}

#[derive(Default)]
pub struct UIState {
    pub screen: Screen,
    pub input: String,
    pub scroll_offset: usize,
    pub is_loading: bool,
    pub status_message: Option<String>,
    
    // Command popup state
    pub command_selection: Option<usize>,
    
    // Debug mode
    pub debug_mode: bool,
    
    // Send animation state (ticks remaining)
    pub send_animation: u8,
    
    // Total lines in chat (for scroll indicator)
    pub total_chat_lines: usize,
    
    // Which panel is focused
    pub focus: Focus,
    
    // Visualization state
    pub show_visualization: bool,
    pub hovered_point: Option<usize>,
    
    // Markdown rendering toggle
    pub show_raw_markdown: bool,
}

impl UIState {
    pub fn new() -> Self {
        Self::default()
    }
}