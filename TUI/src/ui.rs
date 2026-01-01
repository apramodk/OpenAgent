use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, BorderType, Clear, Gauge, Paragraph, Wrap},
    Frame,
};

use crate::app::{App, Role, Screen};

// Copper Sapphire Morning color palette
const BG_DARK: Color = Color::Rgb(12, 12, 16);           // Deep background
const BG_PANEL: Color = Color::Rgb(18, 18, 24);          // Slightly lighter for panels

// Sapphire blues
const SAPPHIRE: Color = Color::Rgb(101, 150, 243);       // #6596F3 - Primary accent
const SAPPHIRE_DARK: Color = Color::Rgb(84, 112, 156);   // #54709C - Darker blue
const CYAN_LIGHT: Color = Color::Rgb(178, 220, 226);     // #B2DCE2 - Light cyan

// Copper/warm tones
const COPPER: Color = Color::Rgb(138, 72, 38);           // #8A4826 - Copper
const WARM_BROWN: Color = Color::Rgb(164, 103, 38);      // #A46726 - Warm brown
const TAN: Color = Color::Rgb(216, 180, 169);            // #D8B4A9 - Tan/beige
const PALE_YELLOW: Color = Color::Rgb(234, 208, 148);    // #EAD094 - Pale yellow

// Accent colors
const BURGUNDY: Color = Color::Rgb(204, 92, 68);         // #CC5C44 - Warnings/errors
const OLIVE: Color = Color::Rgb(131, 179, 102);          // #83B366 - Success/green
const LAVENDER: Color = Color::Rgb(211, 164, 234);       // #D3A4EA - Purple accent

// Text colors
const TEXT_PRIMARY: Color = Color::Rgb(240, 240, 245);   // Near white
const TEXT_SECONDARY: Color = Color::Rgb(180, 180, 190); // Light gray
const TEXT_MUTED: Color = Color::Rgb(105, 116, 133);     // #697485 - Medium gray

// Border colors (subtle)
const BORDER_DIM: Color = Color::Rgb(45, 50, 60);        // Dim border
const BORDER_ACCENT: Color = Color::Rgb(70, 85, 110);    // Accent border

/// Format token counts with smart unit shorthand
fn format_tokens(count: u64) -> String {
    if count < 1_000 {
        format!("{}", count)
    } else if count < 10_000 {
        // Show with comma: 1,234
        let thousands = count / 1_000;
        let remainder = count % 1_000;
        format!("{},{:03}", thousands, remainder)
    } else if count < 1_000_000 {
        // Show in k with 1 decimal: 12.3k
        format!("{:.1}k", count as f64 / 1_000.0)
    } else {
        // Show in M with 2 decimals: 1.23M
        format!("{:.2}M", count as f64 / 1_000_000.0)
    }
}

pub fn draw(frame: &mut Frame, app: &App) {
    // Fill entire background
    let bg = Block::default().style(Style::default().bg(BG_DARK));
    frame.render_widget(bg, frame.area());

    match app.screen {
        Screen::Home => draw_home(frame, app),
        Screen::Chat => draw_chat(frame, app),
    }
}

fn draw_home(frame: &mut Frame, app: &App) {
    let area = frame.area();

    // Subtle background pattern
    draw_background_pattern(frame, area, app.animation_frame);

    // Center content vertically
    let v_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage(25),
            Constraint::Length(12),  // Logo container
            Constraint::Length(3),   // Subtitle
            Constraint::Length(3),   // Hint
            Constraint::Min(0),
        ])
        .split(area);

    // Center horizontally
    let logo_width = 82;
    let h_padding = (area.width.saturating_sub(logo_width)) / 2;
    let logo_area = Rect {
        x: area.x + h_padding,
        y: v_chunks[1].y,
        width: logo_width.min(area.width),
        height: v_chunks[1].height,
    };

    // Glass container for logo (no background, just border)
    draw_glass_border(frame, logo_area, "", app.animation_frame, true);

    // Logo inside
    let inner = Rect {
        x: logo_area.x + 2,
        y: logo_area.y + 1,
        width: logo_area.width.saturating_sub(4),
        height: logo_area.height.saturating_sub(2),
    };

    draw_animated_logo(frame, inner, app.animation_frame);

    // Subtitle with typing animation
    let subtitle_text = "Your AI-powered assistant for navigating large codebases";
    let visible_chars = ((app.animation_frame as f64 / 120.0 * subtitle_text.len() as f64) as usize)
        .min(subtitle_text.len());
    let subtitle = if app.animation_frame < 120 {
        format!("{}|", &subtitle_text[..visible_chars])
    } else {
        subtitle_text.to_string()
    };

    let subtitle_widget = Paragraph::new(subtitle)
        .alignment(Alignment::Center)
        .style(Style::default().fg(TEXT_SECONDARY));
    frame.render_widget(subtitle_widget, v_chunks[2]);

    // Press any key hint with copper glow
    let glow = ((app.animation_frame as f64 / 45.0).sin().abs() * 0.5 + 0.5) as f64;
    let r = (138.0 + (216.0 - 138.0) * glow) as u8;
    let g = (72.0 + (180.0 - 72.0) * glow) as u8;
    let b = (38.0 + (169.0 - 38.0) * glow) as u8;
    let hint_style = Style::default().fg(Color::Rgb(r, g, b));
    let hint = Paragraph::new("[ Press any key to start ]")
        .alignment(Alignment::Center)
        .style(hint_style);
    frame.render_widget(hint, v_chunks[3]);

    // Version info at bottom
    let version_area = Rect {
        x: area.x,
        y: area.height.saturating_sub(2),
        width: area.width,
        height: 1,
    };
    let version = Paragraph::new("v0.1.0")
        .alignment(Alignment::Center)
        .style(Style::default().fg(TEXT_MUTED));
    frame.render_widget(version, version_area);
}

fn draw_background_pattern(frame: &mut Frame, area: Rect, anim_frame: usize) {
    let pattern_offset = (anim_frame / 30) % 4;
    let mut lines: Vec<Line> = Vec::new();

    for y in 0..area.height {
        let mut spans: Vec<Span> = Vec::new();
        for x in 0..area.width {
            let show_dot = ((x as usize + pattern_offset) % 10 == 0) &&
                          ((y as usize + pattern_offset) % 5 == 0);
            if show_dot {
                let brightness = 25 + ((anim_frame as f64 / 60.0 + (x as f64 / 12.0)).sin().abs() * 12.0) as u8;
                spans.push(Span::styled(".", Style::default().fg(Color::Rgb(brightness, brightness + 2, brightness + 5))));
            } else {
                spans.push(Span::raw(" "));
            }
        }
        lines.push(Line::from(spans));
    }

    let pattern = Paragraph::new(lines).style(Style::default().bg(BG_DARK));
    frame.render_widget(pattern, area);
}

fn draw_glass_border(frame: &mut Frame, area: Rect, title: &str, anim_frame: usize, glow: bool) {
    // Animated border - cycles between sapphire and copper
    let border_color = if glow {
        let t = (anim_frame as f64 / 120.0).sin() * 0.5 + 0.5;
        let r = (84.0 + (138.0 - 84.0) * t) as u8;
        let g = (112.0 + (72.0 - 112.0) * t) as u8;
        let b = (156.0 + (38.0 - 156.0) * t) as u8;
        Color::Rgb(r, g, b)
    } else {
        BORDER_DIM
    };

    let block = Block::default()
        .title(Span::styled(title, Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));
        // No background - transparent

    frame.render_widget(block, area);
}

fn draw_animated_logo(frame: &mut Frame, area: Rect, anim_frame: usize) {
    let logo_lines = [
        "",
        " ██████╗ ██████╗ ███████╗███╗   ██╗ █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
        "██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
        "██║   ██║██████╔╝█████╗  ██╔██╗ ██║███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
        "██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
        "╚██████╔╝██║     ███████╗██║ ╚████║██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
        " ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
        "",
        "                    [ AI-Powered Codebase Navigation ]                         ",
    ];

    let mut lines: Vec<Line> = Vec::new();

    for (line_idx, logo_line) in logo_lines.iter().enumerate() {
        let mut spans: Vec<Span> = Vec::new();

        for (char_idx, ch) in logo_line.chars().enumerate() {
            // Wave effect with sapphire-copper gradient
            let wave_offset = (anim_frame as f64 / 25.0) + (char_idx as f64 / 6.0) - (line_idx as f64 / 2.0);
            let wave = (wave_offset.sin() * 0.5 + 0.5) as f64;

            // Cycle: Sapphire -> Copper -> Cyan -> Sapphire
            let phase = ((anim_frame as f64 / 200.0) + (char_idx as f64 / 25.0)) % 3.0;

            let (r, g, b) = if phase < 1.0 {
                // Sapphire to Copper
                let t = phase * wave;
                (
                    (101.0 + (138.0 - 101.0) * t) as u8,
                    (150.0 + (72.0 - 150.0) * t) as u8,
                    (243.0 + (38.0 - 243.0) * t) as u8,
                )
            } else if phase < 2.0 {
                // Copper to Cyan
                let t = (phase - 1.0) * wave;
                (
                    (138.0 + (178.0 - 138.0) * t) as u8,
                    (72.0 + (220.0 - 72.0) * t) as u8,
                    (38.0 + (226.0 - 38.0) * t) as u8,
                )
            } else {
                // Cyan to Sapphire
                let t = (phase - 2.0) * wave;
                (
                    (178.0 + (101.0 - 178.0) * t) as u8,
                    (220.0 + (150.0 - 220.0) * t) as u8,
                    (226.0 + (243.0 - 226.0) * t) as u8,
                )
            };

            spans.push(Span::styled(
                ch.to_string(),
                Style::default().fg(Color::Rgb(r, g, b)),
            ));
        }

        lines.push(Line::from(spans));
    }

    let logo = Paragraph::new(lines).alignment(Alignment::Center);
    frame.render_widget(logo, area);
}

fn draw_chat(frame: &mut Frame, app: &App) {
    let area = frame.area();

    // Main layout with padding
    let padded = Rect {
        x: area.x + 1,
        y: area.y + 1,
        width: area.width.saturating_sub(2),
        height: area.height.saturating_sub(2),
    };

    let main_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(26),  // Sidebar
            Constraint::Length(1),   // Gap
            Constraint::Min(40),     // Chat area
        ])
        .split(padded);

    draw_sidebar(frame, app, main_chunks[0]);
    draw_chat_area(frame, app, main_chunks[2]);

    // Draw command popup if showing
    if app.showing_command_popup() {
        draw_command_popup(frame, app, main_chunks[2]);
    }
}

fn draw_sidebar(frame: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),   // Token monitor
            Constraint::Length(1),   // Gap
            Constraint::Length(5),   // Session info
            Constraint::Min(0),      // Spacer
            Constraint::Length(4),   // Keyboard hints
        ])
        .split(area);

    draw_token_monitor(frame, app, chunks[0]);
    draw_session_info(frame, app, chunks[2]);
    draw_keyboard_hints(frame, chunks[4]);
}

fn draw_token_monitor(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" Tokens ", Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_ACCENT));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let inner_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),  // Total
            Constraint::Length(1),  // Budget bar
            Constraint::Length(1),  // Spacer
            Constraint::Length(1),  // Cost
            Constraint::Length(1),  // Last request
        ])
        .split(inner);

    // Total tokens
    let total = Line::from(vec![
        Span::styled(" # ", Style::default().fg(SAPPHIRE)),
        Span::styled("Total: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(format_tokens(app.tokens.session_total), Style::default().fg(TEXT_PRIMARY).add_modifier(Modifier::BOLD)),
    ]);
    frame.render_widget(Paragraph::new(total), inner_chunks[0]);

    // Budget gauge
    let percentage = app.tokens.budget_percentage().unwrap_or(0.0) / 100.0;
    let gauge_color = if percentage > 0.9 {
        BURGUNDY
    } else if percentage > 0.7 {
        WARM_BROWN
    } else {
        OLIVE
    };

    let gauge = Gauge::default()
        .ratio(percentage.min(1.0))
        .gauge_style(Style::default().fg(gauge_color).bg(BG_PANEL))
        .label("");
    frame.render_widget(gauge, inner_chunks[1]);

    // Cost
    let cost = Line::from(vec![
        Span::styled(" $ ", Style::default().fg(OLIVE)),
        Span::styled("Cost: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(format!("${:.4}", app.tokens.cost_usd), Style::default().fg(OLIVE)),
    ]);
    frame.render_widget(Paragraph::new(cost), inner_chunks[3]);

    // Last request (input+ output-)
    let last = Line::from(vec![
        Span::styled(" ~ ", Style::default().fg(COPPER)),
        Span::styled(format!("{}+ {}-", format_tokens(app.tokens.last_input), format_tokens(app.tokens.last_output)), Style::default().fg(TEXT_SECONDARY)),
    ]);
    frame.render_widget(Paragraph::new(last), inner_chunks[4]);
}

fn draw_session_info(frame: &mut Frame, app: &App, area: Rect) {
    // Show project name in title
    let title = format!(" {} ", app.cwd_name());
    let block = Block::default()
        .title(Span::styled(title, Style::default().fg(COPPER).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_DIM));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let status_color = if app.backend_connected { OLIVE } else { TEXT_MUTED };
    let status_icon = if app.backend_connected { "*" } else { "o" };

    let rag_color = if app.rag.initialized { CYAN_LIGHT } else { TEXT_MUTED };
    let rag_text = if app.rag.initialized {
        format!("{} chunks", app.rag.chunk_count)
    } else {
        "not loaded".to_string()
    };

    let session_text = vec![
        Line::from(vec![
            Span::styled(format!(" {} ", status_icon), Style::default().fg(status_color)),
            Span::styled(if app.backend_connected { "Connected" } else { "Offline" }, Style::default().fg(status_color)),
        ]),
        Line::from(vec![
            Span::styled(" > ", Style::default().fg(SAPPHIRE)),
            Span::styled(format!("{} msgs", app.messages.len()), Style::default().fg(TEXT_PRIMARY)),
        ]),
        Line::from(vec![
            Span::styled(" @ ", Style::default().fg(CYAN_LIGHT)),
            Span::styled(format!("RAG: {}", rag_text), Style::default().fg(rag_color)),
        ]),
    ];

    frame.render_widget(Paragraph::new(session_text), inner);
}

fn draw_keyboard_hints(frame: &mut Frame, area: Rect) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_DIM));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let hints = Paragraph::new(vec![
        Line::from(vec![
            Span::styled("ESC", Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD)),
            Span::styled(" quit", Style::default().fg(TEXT_MUTED)),
        ]),
        Line::from(vec![
            Span::styled("/", Style::default().fg(COPPER).add_modifier(Modifier::BOLD)),
            Span::styled(" commands", Style::default().fg(TEXT_MUTED)),
        ]),
    ])
    .alignment(Alignment::Center);
    frame.render_widget(hints, inner);
}

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    // Calculate input height based on content (min 3, max 8)
    let input_width = area.width.saturating_sub(6) as usize; // Account for borders and prompt
    let input_lines = if input_width > 0 {
        (app.input.len() / input_width) + 1
    } else {
        1
    };
    let input_height = (input_lines as u16 + 2).clamp(3, 8); // +2 for borders

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(5),              // Messages
            Constraint::Length(1),           // Gap
            Constraint::Length(input_height), // Input (dynamic)
        ])
        .split(area);

    draw_messages(frame, app, chunks[0]);
    draw_input(frame, app, chunks[2]);
}

fn draw_messages(frame: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(Span::styled(" Chat ", Style::default().fg(TEXT_PRIMARY).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_DIM));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    if app.messages.is_empty() {
        let empty_msg = Paragraph::new(vec![
            Line::from(""),
            Line::from(""),
            Line::from(Span::styled("No messages yet", Style::default().fg(TEXT_MUTED))),
            Line::from(""),
            Line::from(Span::styled("Type a message or use /help for commands", Style::default().fg(TEXT_MUTED))),
        ])
        .alignment(Alignment::Center);
        frame.render_widget(empty_msg, inner);
        return;
    }

    let mut lines: Vec<Line> = Vec::new();

    for msg in app.messages.iter() {
        let (prefix, prefix_style) = match msg.role {
            Role::User => (
                " > you ",
                Style::default().fg(BG_DARK).bg(SAPPHIRE).add_modifier(Modifier::BOLD),
            ),
            Role::Assistant => (
                " < assistant ",
                Style::default().fg(BG_DARK).bg(COPPER).add_modifier(Modifier::BOLD),
            ),
            Role::System => (
                " * system ",
                Style::default().fg(BG_DARK).bg(WARM_BROWN),
            ),
        };

        lines.push(Line::from(Span::styled(prefix, prefix_style)));

        for line in msg.content.lines() {
            lines.push(Line::from(Span::styled(
                format!("  {}", line),
                Style::default().fg(TEXT_PRIMARY),
            )));
        }
        lines.push(Line::from(""));
    }

    if app.is_loading {
        let dots = match (app.animation_frame / 15) % 4 {
            0 => ".  ",
            1 => ".. ",
            2 => "...",
            _ => " ..",
        };
        lines.push(Line::from(vec![
            Span::styled(" < ", Style::default().fg(COPPER)),
            Span::styled(format!("thinking{}", dots), Style::default().fg(COPPER).add_modifier(Modifier::ITALIC)),
        ]));
    }

    let messages = Paragraph::new(lines)
        .wrap(Wrap { trim: false })
        .scroll((app.scroll_offset as u16, 0));

    frame.render_widget(messages, inner);
}

fn draw_input(frame: &mut Frame, app: &App, area: Rect) {
    // Pulsing border
    let glow = ((app.animation_frame as f64 / 90.0).sin() * 0.3 + 0.7) as f64;
    let r = (101.0 * glow) as u8;
    let g = (150.0 * glow) as u8;
    let b = (243.0 * glow) as u8;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(r, g, b)));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let cursor = if app.animation_frame % 30 < 15 { "|" } else { " " };
    let input_text = format!(" > {}{}", app.input, cursor);

    let input = Paragraph::new(input_text)
        .style(Style::default().fg(TEXT_PRIMARY))
        .wrap(Wrap { trim: false });
    frame.render_widget(input, inner);
}

fn draw_command_popup(frame: &mut Frame, app: &App, chat_area: Rect) {
    // Get filtered commands from app
    let filtered = app.get_filtered_commands();

    if filtered.is_empty() {
        return;
    }

    // +1 for the "your input" option, +2 for borders
    let popup_height = (filtered.len() + 3) as u16;
    let popup_width = 44.min(chat_area.width.saturating_sub(4));
    let popup_x = chat_area.x + 2;
    let popup_y = chat_area.y + chat_area.height.saturating_sub(popup_height + 4);

    let popup_area = Rect {
        x: popup_x,
        y: popup_y,
        width: popup_width,
        height: popup_height,
    };

    // Clear area behind popup
    frame.render_widget(Clear, popup_area);

    // Popup border
    let block = Block::default()
        .title(Span::styled(" Commands ", Style::default().fg(COPPER).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COPPER))
        .style(Style::default().bg(BG_PANEL));

    let inner = block.inner(popup_area);
    frame.render_widget(block, popup_area);

    // Command list with "your input" option first
    let mut lines: Vec<Line> = Vec::new();

    // First option: current typed input (selected when command_selection is None)
    let input_selected = app.command_selection.is_none();
    let input_style = if input_selected {
        Style::default().fg(CYAN_LIGHT).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(TEXT_SECONDARY)
    };
    let indicator = if input_selected { ">" } else { " " };
    lines.push(Line::from(vec![
        Span::styled(format!("{} {} ", indicator, &app.input), input_style),
        Span::styled("(your input)", Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
    ]));

    // Command options
    for (i, (cmd, desc)) in filtered.iter().enumerate() {
        let is_selected = app.command_selection == Some(i);
        let style = if is_selected {
            Style::default().fg(CYAN_LIGHT).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(TEXT_SECONDARY)
        };
        let indicator = if is_selected { ">" } else { " " };

        lines.push(Line::from(vec![
            Span::styled(format!("{} {} ", indicator, cmd), style),
            Span::styled(format!("- {}", desc), Style::default().fg(TEXT_MUTED)),
        ]));
    }

    let list = Paragraph::new(lines);
    frame.render_widget(list, inner);
}
