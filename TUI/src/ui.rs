use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, BorderType, Clear, Gauge, Paragraph, Wrap},
    Frame,
};

use crate::app::{App, Role};
use crate::ui_state::Screen;
use crate::markdown;
use crate::config::COMING_SOON;

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

// Code block colors (for raw markdown view)
const CODE_BG: Color = Color::Rgb(40, 44, 52);           // Dark background
const CODE_FG: Color = Color::Rgb(171, 178, 191);        // Light gray text

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

    match app.ui.screen {
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

    // Simple twinkling starfield background
    let mut lines: Vec<Line> = Vec::new();

    for y in 0..area.height as usize {
        let mut spans: Vec<Span> = Vec::new();
        for x in 0..area.width as usize {
            let show_star = ((x + pattern_offset) % 12 == 0) && ((y + pattern_offset) % 6 == 0);
            if show_star {
                let brightness = 25 + ((anim_frame as f64 / 60.0 + (x as f64 / 12.0)).sin().abs() * 15.0) as u8;
                let color = Color::Rgb(brightness, brightness + 2, brightness + 5);
                spans.push(Span::styled(".", Style::default().fg(color)));
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

    // Draw activity popup if visible
    if app.activity.visible {
        draw_activity_popup(frame, app, main_chunks[2]);
    }

    // Draw debug overlay if enabled
    if app.ui.debug_mode {
        draw_debug_overlay(frame, app, area);
    }
}

fn draw_sidebar(frame: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),   // Token monitor
            Constraint::Length(1),   // Gap
            Constraint::Length(5),   // Session info
            Constraint::Length(1),   // Gap
            Constraint::Min(6),      // Coming soon
            Constraint::Length(4),   // Keyboard hints
        ])
        .split(area);

    draw_token_monitor(frame, app, chunks[0]);
    draw_session_info(frame, app, chunks[2]);
    draw_coming_soon(frame, app, chunks[4]);
    draw_keyboard_hints(frame, chunks[5]);
}

fn draw_token_monitor(frame: &mut Frame, app: &App, area: Rect) {
    // Title shows connection status
    let (title, title_color) = if !app.backend_connected {
        (" Tokens (offline) ", TEXT_MUTED)
    } else if app.tokens.session_total == 0 {
        (" Tokens (idle) ", TEXT_MUTED)
    } else {
        (" Tokens ", SAPPHIRE)
    };

    let block = Block::default()
        .title(Span::styled(title, Style::default().fg(title_color).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_ACCENT));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Show helpful message if no LLM activity
    if !app.backend_connected {
        let offline_msg = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled(" Not connected", Style::default().fg(BURGUNDY))),
            Line::from(Span::styled(" to Python backend", Style::default().fg(TEXT_MUTED))),
            Line::from(""),
            Line::from(Span::styled(" Run without -o flag", Style::default().fg(TEXT_MUTED))),
        ]);
        frame.render_widget(offline_msg, inner);
        return;
    }

    if app.tokens.session_total == 0 {
        let idle_msg = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled(" No LLM calls yet", Style::default().fg(TEXT_MUTED))),
            Line::from(""),
            Line::from(Span::styled(" Send a message to", Style::default().fg(TEXT_MUTED))),
            Line::from(Span::styled(" start tracking", Style::default().fg(TEXT_MUTED))),
        ]);
        frame.render_widget(idle_msg, inner);
        return;
    }

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

fn draw_coming_soon(frame: &mut Frame, app: &App, area: Rect) {
    // Animated bullet shapes that cycle
    let bullet_shapes = ["◇", "◆", "○", "●", "□", "■", "△", "▲"];

    let block = Block::default()
        .title(Span::styled(" Soon ", Style::default().fg(TEXT_MUTED)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER_DIM));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Fireplace animation - wood logs with flickering flames
    let fire_height = 4;
    let items_height = inner.height as usize;

    // Reserve space for fireplace at bottom
    let show_fire = items_height >= fire_height + 2;
    let items_available = if show_fire {
        items_height.saturating_sub(fire_height + 1)
    } else {
        items_height
    };

    let max_items = items_available.min(COMING_SOON.len());
    let mut lines: Vec<Line> = Vec::new();

    for (i, &feature) in COMING_SOON.iter().take(max_items).enumerate() {
        // Each item gets a different phase offset for the animation
        let bullet_idx = ((app.animation_frame / 20) + i * 2) % bullet_shapes.len();
        let bullet = bullet_shapes[bullet_idx];

        // Subtle color animation - very muted
        let phase = ((app.animation_frame as f64 / 180.0) + (i as f64 * 0.3)).sin() * 0.15 + 0.35;
        let gray = (105.0 * phase + 60.0) as u8;
        let bullet_color = Color::Rgb(gray, gray + 5, gray + 15);

        // Truncate feature name if needed
        let max_len = (inner.width as usize).saturating_sub(3);
        let display: String = feature.chars().take(max_len).collect();

        lines.push(Line::from(vec![
            Span::styled(format!(" {} ", bullet), Style::default().fg(bullet_color)),
            Span::styled(display, Style::default().fg(TEXT_MUTED)),
        ]));
    }

    // Add fireplace at bottom center if space allows
    if show_fire {
        // Calculate how many empty lines needed to push fire to bottom
        // Fire takes 4 lines (3 flame + 1 wood) + 1 separator = 5 lines
        let fire_total_lines = 5;
        let content_lines = lines.len();
        let total_height = inner.height as usize;
        let empty_lines_needed = total_height.saturating_sub(content_lines + fire_total_lines);

        // Add empty lines to push fire to bottom
        for _ in 0..empty_lines_needed {
            lines.push(Line::from(""));
        }
        // Flame colors with flickering
        let t = app.animation_frame as f64 / 6.0;

        // Create flickering intensities for different parts
        let f1 = ((t).sin() * 0.5 + 0.5) as f64;
        let f2 = ((t * 1.4 + 1.0).sin() * 0.5 + 0.5) as f64;
        let f3 = ((t * 0.8 + 2.0).sin() * 0.5 + 0.5) as f64;
        let f4 = ((t * 1.2 + 0.5).sin() * 0.5 + 0.5) as f64;

        // Color palette for fire (from hot to cool)
        let white_hot = Color::Rgb(255, (255.0 * (0.9 + f1 * 0.1)) as u8, (200.0 * f2) as u8);
        let yellow = Color::Rgb(255, (220.0 * (0.8 + f2 * 0.2)) as u8, (50.0 * f3) as u8);
        let orange = Color::Rgb(255, (140.0 * (0.7 + f1 * 0.3)) as u8, 0);
        let red_orange = Color::Rgb((255.0 * (0.8 + f3 * 0.2)) as u8, (80.0 * (0.6 + f2 * 0.4)) as u8, 0);
        let red = Color::Rgb((200.0 * (0.7 + f4 * 0.3)) as u8, (40.0 * f1) as u8, 0);
        let dark_red = Color::Rgb((120.0 * (0.6 + f2 * 0.4)) as u8, 0, 0);

        // Wood colors with ember glow
        let ember = ((t * 0.3).sin() * 0.4 + 0.6) as f64;
        let wood = Color::Rgb((100.0 * ember) as u8, (50.0 * ember) as u8, (20.0 * ember) as u8);
        let wood_dark = Color::Rgb(60, 30, 10);

        // Calculate centering (fire is 9 chars wide)
        let fire_width = 9;
        let box_width = inner.width as usize;
        let left_pad = box_width.saturating_sub(fire_width) / 2;
        let pad = " ".repeat(left_pad);

        // Animation frame for flame shape with smooth perpetual bounce
        // Uses sine wave for natural easing - slows at edges, fast in middle
        // This creates smooth, organic bouncing motion
        let t = app.animation_frame as f64 / 40.0; // Slow, smooth oscillation
        let sine_val = t.sin(); // Oscillates -1 to 1 perpetually
        let normalized = (sine_val + 1.0) / 2.0; // Now 0.0 to 1.0
        let frame = (normalized * 5.0).round() as usize; // 0 to 5

        lines.push(Line::from(""));

        // Pixel art fire using block characters: ░▒▓█▀▄
        // Tips dance left-right-center in a loop, flames flicker
        match frame {
            0 => {
                // Tips: left side
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled(" ", Style::default()),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("      ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▄", Style::default().fg(white_hot)),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("     ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("▄", Style::default().fg(red_orange)),
                    Span::styled("    ", Style::default()),
                ]));
            }
            1 => {
                // Tips: left-center
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("  ", Style::default()),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("▀", Style::default().fg(white_hot)),
                    Span::styled("     ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled(" ", Style::default()),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("█", Style::default().fg(white_hot)),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("    ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(red_orange)),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled("   ", Style::default()),
                ]));
            }
            2 => {
                // Tips: center
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("   ", Style::default()),
                    Span::styled("▄", Style::default().fg(white_hot)),
                    Span::styled("▀", Style::default().fg(yellow)),
                    Span::styled("    ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("  ", Style::default()),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("█", Style::default().fg(white_hot)),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("   ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled(" ", Style::default()),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▄", Style::default().fg(red)),
                ]));
            }
            3 => {
                // Tips: right-center
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("    ", Style::default()),
                    Span::styled("▀", Style::default().fg(yellow)),
                    Span::styled("▄", Style::default().fg(white_hot)),
                    Span::styled("   ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("   ", Style::default()),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(white_hot)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("  ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("  ", Style::default()),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled("▓", Style::default().fg(red_orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled(" ", Style::default()),
                ]));
            }
            4 => {
                // Tips: right side
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("      ", Style::default()),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("  ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("    ", Style::default()),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("▄", Style::default().fg(white_hot)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled(" ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("   ", Style::default()),
                    Span::styled("▄", Style::default().fg(red_orange)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled(" ", Style::default()),
                ]));
            }
            _ => {
                // Tips: back to right-center (frame 5)
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("     ", Style::default()),
                    Span::styled("▄", Style::default().fg(white_hot)),
                    Span::styled("▄", Style::default().fg(yellow)),
                    Span::styled("  ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("   ", Style::default()),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("█", Style::default().fg(white_hot)),
                    Span::styled("▄", Style::default().fg(orange)),
                    Span::styled("  ", Style::default()),
                ]));
                lines.push(Line::from(vec![
                    Span::raw(pad.clone()),
                    Span::styled("  ", Style::default()),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled("█", Style::default().fg(red_orange)),
                    Span::styled("▓", Style::default().fg(orange)),
                    Span::styled("█", Style::default().fg(yellow)),
                    Span::styled("▓", Style::default().fg(red_orange)),
                    Span::styled("▄", Style::default().fg(red)),
                    Span::styled(" ", Style::default()),
                ]));
            }
        }

        // Wood logs (static but with ember glow)
        lines.push(Line::from(vec![
            Span::raw(pad.clone()),
            Span::styled("▄", Style::default().fg(wood_dark)),
            Span::styled("███", Style::default().fg(wood)),
            Span::styled("▓", Style::default().fg(red)),
            Span::styled("███", Style::default().fg(wood)),
            Span::styled("▄", Style::default().fg(wood_dark)),
        ]));
    }

    let content = Paragraph::new(lines);
    frame.render_widget(content, inner);
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
            Span::styled(" quit  ", Style::default().fg(TEXT_MUTED)),
            Span::styled("/", Style::default().fg(COPPER).add_modifier(Modifier::BOLD)),
            Span::styled(" cmds", Style::default().fg(TEXT_MUTED)),
        ]),
        Line::from(vec![
            Span::styled("F2", Style::default().fg(LAVENDER).add_modifier(Modifier::BOLD)),
            Span::styled(" md toggle", Style::default().fg(TEXT_MUTED)),
        ]),
    ])
    .alignment(Alignment::Center);
    frame.render_widget(hints, inner);
}

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    // Calculate input height based on content (min 3, max 8)
    let input_width = area.width.saturating_sub(6) as usize; // Account for borders and prompt
    let input_lines = if input_width > 0 {
        (app.ui.input.len() / input_width) + 1
    } else {
        1
    };
    let input_height = (input_lines as u16 + 2).clamp(3, 8); // +2 for borders

    if app.ui.show_visualization {
        // Split horizontally: chat on left, visualization on right
        let h_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(50),  // Chat + input
                Constraint::Length(1),       // Gap
                Constraint::Percentage(50),  // Visualization
            ])
            .split(area);

        // Chat area (left side)
        let v_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(5),              // Messages
                Constraint::Length(1),           // Gap
                Constraint::Length(input_height), // Input (dynamic)
            ])
            .split(h_chunks[0]);

        draw_messages(frame, app, v_chunks[0]);
        draw_input(frame, app, v_chunks[2]);

        // Visualization (right side)
        draw_visualization(frame, app, h_chunks[2]);
    } else {
        // Normal layout without visualization
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
}

fn draw_messages(frame: &mut Frame, app: &App, area: Rect) {
    use crate::ui_state::Focus;

    // Border color based on focus and animation
    let border_color = if app.ui.send_animation > 0 {
        // Animate border on send
        let intensity = app.ui.send_animation as f64 / 20.0;
        let r = (101.0 + (154.0 * intensity)) as u8;
        let g = (150.0 + (70.0 * intensity)) as u8;
        let b = (243.0 - (17.0 * intensity)) as u8;
        Color::Rgb(r, g, b)
    } else if app.ui.focus == Focus::Chat {
        SAPPHIRE  // Highlighted when focused
    } else {
        BORDER_DIM
    };

    let block = Block::default()
        .title(Span::styled(" Chat ", Style::default().fg(TEXT_PRIMARY).add_modifier(Modifier::BOLD)))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Add padding inside the chat area
    let padded = Rect {
        x: inner.x + 1,
        y: inner.y + 1,
        width: inner.width.saturating_sub(2),
        height: inner.height.saturating_sub(2),
    };

    if app.messages.is_empty() {
        // Welcome screen with logo when no messages
        let welcome_lines = vec![
            Line::from(""),
            Line::from(vec![
                Span::styled("╭───────────────────────────────────────╮", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
                Span::styled("                                       ", Style::default()),
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
                Span::styled("      ◆ ", Style::default().fg(COPPER)),
                Span::styled("O P E N A G E N T", Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD)),
                Span::styled(" ◆      ", Style::default().fg(COPPER)),
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
                Span::styled("                                       ", Style::default()),
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
                Span::styled("   AI-powered codebase navigation      ", Style::default().fg(TEXT_MUTED)),
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
                Span::styled("                                       ", Style::default()),
                Span::styled("│", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("╰───────────────────────────────────────╯", Style::default().fg(BORDER_ACCENT)),
            ]),
            Line::from(""),
            Line::from(""),
            Line::from(vec![
                Span::styled("  Ask me anything about your codebase:", Style::default().fg(TEXT_SECONDARY)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("    • ", Style::default().fg(COPPER)),
                Span::styled("\"How does the auth system work?\"", Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
            ]),
            Line::from(vec![
                Span::styled("    • ", Style::default().fg(COPPER)),
                Span::styled("\"Find where errors are handled\"", Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
            ]),
            Line::from(vec![
                Span::styled("    • ", Style::default().fg(COPPER)),
                Span::styled("\"Explain this function\"", Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
            ]),
            Line::from(""),
            Line::from(""),
            Line::from(vec![
                Span::styled("  Type a message below or use ", Style::default().fg(TEXT_MUTED)),
                Span::styled("/help", Style::default().fg(SAPPHIRE)),
                Span::styled(" for commands", Style::default().fg(TEXT_MUTED)),
            ]),
        ];

        let welcome = Paragraph::new(welcome_lines).alignment(Alignment::Center);
        frame.render_widget(welcome, padded);
        return;
    }

    // Fixed-width label for alignment
    const LABEL_WIDTH: usize = 12;
    let indent: String = " ".repeat(LABEL_WIDTH);
    let content_width = padded.width as usize - LABEL_WIDTH;

    // Helper to wrap text manually while preserving alignment
    fn wrap_text(text: &str, max_width: usize) -> Vec<String> {
        if max_width == 0 {
            return vec![text.to_string()];
        }
        let mut result = Vec::new();
        let mut current_line = String::new();

        for word in text.split_whitespace() {
            if current_line.is_empty() {
                current_line = word.to_string();
            } else if current_line.len() + 1 + word.len() <= max_width {
                current_line.push(' ');
                current_line.push_str(word);
            } else {
                result.push(current_line);
                current_line = word.to_string();
            }
        }
        if !current_line.is_empty() {
            result.push(current_line);
        }
        if result.is_empty() {
            result.push(String::new());
        }
        result
    }

    let mut lines: Vec<Line> = Vec::new();
    let msg_count = app.messages.len();

    for (msg_idx, msg) in app.messages.iter().enumerate() {
        let is_last_user_msg = msg_idx == msg_count - 1 && matches!(msg.role, Role::User);

        // Slide-in effect for the last sent message
        let slide_offset = if is_last_user_msg && app.ui.send_animation > 10 {
            20 - (20 - app.ui.send_animation) as usize
        } else {
            0
        };

        let (label, label_style, content_style) = match msg.role {
            Role::User => (
                "you",
                Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD),
                Style::default().fg(TEXT_PRIMARY),
            ),
            Role::Assistant => (
                "assistant",
                Style::default().fg(COPPER).add_modifier(Modifier::BOLD),
                Style::default().fg(TEXT_PRIMARY),
            ),
            Role::System => (
                "system",
                Style::default().fg(WARM_BROWN).add_modifier(Modifier::BOLD),
                Style::default().fg(TEXT_MUTED),
            ),
        };

        // Format label with fixed width and separator
        let formatted_label = format!("{:>width$} │ ", label, width = LABEL_WIDTH - 3);
        let slide_padding = " ".repeat(slide_offset);

        // Check if this is an assistant message (render in card)
        let is_assistant = matches!(msg.role, Role::Assistant);

        if is_assistant {
            // Render assistant message in a card with toggle button
            // Use a fixed card width for consistent borders
            let card_width = content_width.saturating_sub(4);
            let inner_width = card_width.saturating_sub(4); // "│ " on left, " │" on right

            // Helper to calculate visible character width of spans
            fn spans_width(spans: &[Span]) -> usize {
                spans.iter().map(|s| s.content.chars().count()).sum()
            }

            // Top border: ╭─[toggle]────────────────────╮
            let toggle_text = if app.ui.show_raw_markdown { "○ Raw" } else { "◉ Preview" };
            let toggle_style = if app.ui.show_raw_markdown {
                Style::default().fg(TEXT_MUTED)
            } else {
                Style::default().fg(CYAN_LIGHT)
            };
            // Total top: ╭─[ + toggle + ]─────╮ = 4 + toggle_len + remaining + 1
            let top_used = 4 + toggle_text.chars().count(); // ╭─[ ]
            let top_fill = card_width.saturating_sub(top_used + 1); // -1 for ╮

            lines.push(Line::from(vec![
                Span::raw(slide_padding.clone()),
                Span::styled(formatted_label.clone(), label_style),
                Span::styled("╭─[", Style::default().fg(BORDER_ACCENT)),
                Span::styled(toggle_text, toggle_style),
                Span::styled("]", Style::default().fg(BORDER_ACCENT)),
                Span::styled("─".repeat(top_fill), Style::default().fg(BORDER_ACCENT)),
                Span::styled("╮", Style::default().fg(BORDER_ACCENT)),
            ]));

            // Content lines - wrapped text with proper padding
            let content_lines: Vec<String> = if app.ui.show_raw_markdown {
                // Raw mode - show source
                msg.content.lines()
                    .flat_map(|line| wrap_text(line, inner_width))
                    .collect()
            } else {
                // Preview mode - for now, also wrap plain text
                // The markdown styling happens via spans, but we need consistent wrapping
                msg.content.lines()
                    .flat_map(|line| wrap_text(line, inner_width))
                    .collect()
            };

            // Render content with proper styling
            if content_lines.is_empty() {
                // Empty content - single padded line
                lines.push(Line::from(vec![
                    Span::raw(slide_padding.clone()),
                    Span::styled(indent.clone(), Style::default()),
                    Span::styled("│ ", Style::default().fg(BORDER_ACCENT)),
                    Span::raw(" ".repeat(inner_width)),
                    Span::styled(" │", Style::default().fg(BORDER_ACCENT)),
                ]));
            } else if app.ui.show_raw_markdown {
                // Raw mode - code styling with exact padding
                for line_text in content_lines.iter() {
                    let padded = format!("{:<width$}", line_text, width = inner_width);
                    lines.push(Line::from(vec![
                        Span::raw(slide_padding.clone()),
                        Span::styled(indent.clone(), Style::default()),
                        Span::styled("│ ", Style::default().fg(BORDER_ACCENT)),
                        Span::styled(padded, Style::default().fg(CODE_FG).bg(CODE_BG)),
                        Span::styled(" │", Style::default().fg(BORDER_ACCENT)),
                    ]));
                }
            } else {
                // Preview mode - parse markdown and render with styling
                let elements = markdown::parse_markdown(&msg.content);
                let md_lines = markdown::render_markdown(&elements, inner_width);

                if md_lines.is_empty() {
                    lines.push(Line::from(vec![
                        Span::raw(slide_padding.clone()),
                        Span::styled(indent.clone(), Style::default()),
                        Span::styled("│ ", Style::default().fg(BORDER_ACCENT)),
                        Span::raw(" ".repeat(inner_width)),
                        Span::styled(" │", Style::default().fg(BORDER_ACCENT)),
                    ]));
                } else {
                    for md_line in md_lines.iter() {
                        let content_w = spans_width(&md_line.spans);
                        let padding_needed = inner_width.saturating_sub(content_w);

                        let mut spans = vec![
                            Span::raw(slide_padding.clone()),
                            Span::styled(indent.clone(), Style::default()),
                            Span::styled("│ ", Style::default().fg(BORDER_ACCENT)),
                        ];
                        spans.extend(md_line.spans.iter().cloned());
                        spans.push(Span::raw(" ".repeat(padding_needed)));
                        spans.push(Span::styled(" │", Style::default().fg(BORDER_ACCENT)));
                        lines.push(Line::from(spans));
                    }
                }
            }

            // Bottom border: ╰────────────────────F2:toggle─╯
            let hint_text = "F2:toggle";
            let bottom_used = 2 + hint_text.len(); // ╰ + hint + ─╯
            let bottom_fill = card_width.saturating_sub(bottom_used);

            lines.push(Line::from(vec![
                Span::raw(slide_padding.clone()),
                Span::styled(indent.clone(), Style::default()),
                Span::styled("╰", Style::default().fg(BORDER_ACCENT)),
                Span::styled("─".repeat(bottom_fill), Style::default().fg(BORDER_ACCENT)),
                Span::styled(hint_text, Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
                Span::styled("─╯", Style::default().fg(BORDER_ACCENT)),
            ]));
        } else {
            // User and System messages - original inline rendering
            let mut is_first_line = true;
            for content_line in msg.content.lines() {
                // Wrap each line of content
                let wrapped = wrap_text(content_line, content_width.saturating_sub(2));

                for (wrap_idx, wrapped_line) in wrapped.iter().enumerate() {
                    if is_first_line && wrap_idx == 0 {
                        // First line of message - show label
                        lines.push(Line::from(vec![
                            Span::raw(slide_padding.clone()),
                            Span::styled(formatted_label.clone(), label_style),
                            Span::styled(wrapped_line.clone(), content_style),
                        ]));
                        is_first_line = false;
                    } else {
                        // Continuation lines - indent to align with content
                        lines.push(Line::from(vec![
                            Span::raw(slide_padding.clone()),
                            Span::styled(indent.clone(), Style::default()),
                            Span::styled(wrapped_line.clone(), content_style),
                        ]));
                    }
                }
            }
        }

        // Add spacing between messages
        lines.push(Line::from(""));
    }

    if app.ui.is_loading {
        let dots = match (app.animation_frame / 15) % 4 {
            0 => ".  ",
            1 => ".. ",
            2 => "...",
            _ => " ..",
        };
        let formatted_label = format!("{:>width$} │ ", "assistant", width = LABEL_WIDTH - 3);
        lines.push(Line::from(vec![
            Span::styled(formatted_label, Style::default().fg(COPPER).add_modifier(Modifier::BOLD)),
            Span::styled(format!("thinking{}", dots), Style::default().fg(COPPER).add_modifier(Modifier::ITALIC)),
        ]));
    }

    let total_lines = lines.len();
    let visible_height = padded.height as usize;

    // Calculate scroll - scroll from bottom, clamp scroll_offset to valid range
    let max_scroll = total_lines.saturating_sub(visible_height);
    let clamped_offset = app.ui.scroll_offset.min(max_scroll);
    let scroll_pos = max_scroll.saturating_sub(clamped_offset);

    // No Wrap needed - we handle it manually for proper alignment
    let messages = Paragraph::new(lines)
        .scroll((scroll_pos as u16, 0));

    frame.render_widget(messages, padded);

    // Draw scroll indicator if needed
    if total_lines > visible_height {
        let can_scroll_up = scroll_pos > 0;
        let can_scroll_down = clamped_offset > 0;

        // Show scroll arrows on the right edge
        if can_scroll_up {
            let up_indicator = Paragraph::new("▲")
                .style(Style::default().fg(SAPPHIRE));
            let up_area = Rect {
                x: area.x + area.width - 2,
                y: area.y + 1,
                width: 1,
                height: 1,
            };
            frame.render_widget(up_indicator, up_area);
        }

        if can_scroll_down {
            let down_indicator = Paragraph::new("▼")
                .style(Style::default().fg(SAPPHIRE));
            let down_area = Rect {
                x: area.x + area.width - 2,
                y: area.y + area.height - 2,
                width: 1,
                height: 1,
            };
            frame.render_widget(down_indicator, down_area);
        }

        // Show scroll position percentage
        let scroll_pct = if max_scroll > 0 {
            ((max_scroll - scroll_pos) * 100 / max_scroll) as u8
        } else {
            100
        };
        if scroll_pct < 100 {
            let scroll_text = format!("{}%", scroll_pct);
            let scroll_widget = Paragraph::new(scroll_text)
                .style(Style::default().fg(TEXT_MUTED));
            let scroll_area = Rect {
                x: area.x + area.width - 5,
                y: area.y,
                width: 4,
                height: 1,
            };
            frame.render_widget(scroll_widget, scroll_area);
        }
    }
}

fn draw_input(frame: &mut Frame, app: &App, area: Rect) {
    use crate::ui_state::Focus;

    // Border color based on focus - pulse when focused, dim when not
    let border_color = if app.ui.focus == Focus::Input {
        // Pulsing border when focused
        let glow = ((app.animation_frame as f64 / 90.0).sin() * 0.3 + 0.7) as f64;
        let r = (101.0 * glow) as u8;
        let g = (150.0 * glow) as u8;
        let b = (243.0 * glow) as u8;
        Color::Rgb(r, g, b)
    } else {
        BORDER_DIM
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let cursor = if app.animation_frame % 30 < 15 { "|" } else { " " };
    let input_text = format!(" > {}{}", app.ui.input, cursor);

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
    let input_selected = app.ui.command_selection.is_none();
    let input_style = if input_selected {
        Style::default().fg(CYAN_LIGHT).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(TEXT_SECONDARY)
    };
    let indicator = if input_selected { ">" } else { " " };
    lines.push(Line::from(vec![
        Span::styled(format!("{} {} ", indicator, &app.ui.input), input_style),
        Span::styled("(your input)", Style::default().fg(TEXT_MUTED).add_modifier(Modifier::ITALIC)),
    ]));

    // Command options
    for (i, (cmd, desc)) in filtered.iter().enumerate() {
        let is_selected = app.ui.command_selection == Some(i);
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

/// Draw a glassy debug overlay panel
fn draw_debug_overlay(frame: &mut Frame, app: &App, area: Rect) {
    // Position in top-right corner
    let overlay_width = 50.min(area.width.saturating_sub(8));
    let overlay_height = 18.min(area.height.saturating_sub(4));
    let overlay_x = area.x + area.width.saturating_sub(overlay_width + 2);
    let overlay_y = area.y + 2;

    let overlay_area = Rect {
        x: overlay_x,
        y: overlay_y,
        width: overlay_width,
        height: overlay_height,
    };

    // Clear and draw semi-transparent background
    frame.render_widget(Clear, overlay_area);

    // Glassy background color (slightly lighter than BG_DARK with blue tint)
    let glass_bg = Color::Rgb(20, 24, 35);

    // Animated border - pulsing cyan/sapphire
    let pulse = ((app.animation_frame as f64 / 60.0).sin() * 0.3 + 0.7) as f64;
    let border_r = (100.0 * pulse) as u8;
    let border_g = (180.0 * pulse) as u8;
    let border_b = (220.0 * pulse) as u8;

    let block = Block::default()
        .title(Span::styled(
            " DEBUG ",
            Style::default()
                .fg(Color::Rgb(255, 180, 100))
                .add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(Color::Rgb(border_r, border_g, border_b)))
        .style(Style::default().bg(glass_bg));

    let inner = block.inner(overlay_area);
    frame.render_widget(block, overlay_area);

    // Debug content
    let mut lines: Vec<Line> = Vec::new();

    // Header with path
    lines.push(Line::from(vec![
        Span::styled("  cwd: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(
            app.cwd.file_name().and_then(|n| n.to_str()).unwrap_or("?"),
            Style::default().fg(CYAN_LIGHT),
        ),
    ]));
    lines.push(Line::from(""));

    // Status section
    lines.push(Line::from(vec![
        Span::styled("  ● ", Style::default().fg(if app.backend_connected { OLIVE } else { BURGUNDY })),
        Span::styled("Backend: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(
            if app.backend_connected { "connected" } else { "disconnected" },
            Style::default().fg(if app.backend_connected { OLIVE } else { BURGUNDY }),
        ),
    ]));

    lines.push(Line::from(vec![
        Span::styled("  ● ", Style::default().fg(if app.rag.initialized { CYAN_LIGHT } else { TEXT_MUTED })),
        Span::styled("RAG: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(
            format!("{} chunks", app.rag.chunk_count),
            Style::default().fg(CYAN_LIGHT),
        ),
    ]));
    lines.push(Line::from(""));

    // Token stats
    lines.push(Line::from(vec![
        Span::styled("  Tokens: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(
            format_tokens(app.tokens.session_total),
            Style::default().fg(SAPPHIRE).add_modifier(Modifier::BOLD),
        ),
        Span::styled(" (", Style::default().fg(TEXT_MUTED)),
        Span::styled(format!("${:.4}", app.tokens.cost_usd), Style::default().fg(OLIVE)),
        Span::styled(")", Style::default().fg(TEXT_MUTED)),
    ]));

    lines.push(Line::from(vec![
        Span::styled("  Last: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(format!("{}↑ ", format_tokens(app.tokens.last_input)), Style::default().fg(COPPER)),
        Span::styled(format!("{}↓", format_tokens(app.tokens.last_output)), Style::default().fg(SAPPHIRE)),
    ]));
    lines.push(Line::from(""));

    // Messages summary
    lines.push(Line::from(vec![
        Span::styled("  Messages: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(format!("{}", app.messages.len()), Style::default().fg(TEXT_PRIMARY)),
    ]));

    // Show last message preview
    if let Some(last_msg) = app.messages.back() {
        let role_str = match last_msg.role {
            crate::app::Role::User => "user",
            crate::app::Role::Assistant => "asst",
            crate::app::Role::System => "sys",
        };
        let preview: String = last_msg.content.chars().take(30).collect();
        let preview = if last_msg.content.len() > 30 {
            format!("{}...", preview)
        } else {
            preview
        };
        lines.push(Line::from(vec![
            Span::styled(format!("  [{}] ", role_str), Style::default().fg(COPPER)),
            Span::styled(preview, Style::default().fg(TEXT_SECONDARY)),
        ]));
    }
    lines.push(Line::from(""));

    // Input buffer
    let input_preview: String = app.ui.input.chars().take(35).collect();
    lines.push(Line::from(vec![
        Span::styled("  Input: ", Style::default().fg(TEXT_MUTED)),
        Span::styled(
            if input_preview.is_empty() { "(empty)" } else { &input_preview },
            Style::default().fg(if input_preview.is_empty() { TEXT_MUTED } else { TEXT_PRIMARY }),
        ),
    ]));
    lines.push(Line::from(""));

    // Footer hint
    lines.push(Line::from(vec![
        Span::styled("  ", Style::default()),
        Span::styled("/debug", Style::default().fg(COPPER)),
        Span::styled(" to close │ ", Style::default().fg(TEXT_MUTED)),
        Span::styled("/copy", Style::default().fg(COPPER)),
        Span::styled(" to export", Style::default().fg(TEXT_MUTED)),
    ]));

    let debug_content = Paragraph::new(lines);
    frame.render_widget(debug_content, inner);
}

/// Draw activity log popup showing what's happening
fn draw_activity_popup(frame: &mut Frame, app: &App, chat_area: Rect) {
    if app.activity.entries.is_empty() {
        return;
    }

    // Spinner frames for pending activities
    let spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    let spinner_idx = (app.animation_frame / 6) % spinner_frames.len();
    let spinner = spinner_frames[spinner_idx];

    // Position above the input area (bottom left of chat area)
    let popup_height = (app.activity.entries.len() as u16 + 2).min(10);
    let popup_width = 50.min(chat_area.width.saturating_sub(8));
    let popup_x = chat_area.x + 2;
    let popup_y = chat_area.y + 2;

    let popup_area = Rect {
        x: popup_x,
        y: popup_y,
        width: popup_width,
        height: popup_height,
    };

    // Clear area behind popup
    frame.render_widget(Clear, popup_area);

    // Glass background
    let glass_bg = Color::Rgb(16, 20, 28);

    // Animated border - pulsing sapphire when active
    let has_pending = app.activity.has_pending();
    let pulse = if has_pending {
        ((app.animation_frame as f64 / 30.0).sin() * 0.3 + 0.7) as f64
    } else {
        0.5
    };
    let border_r = (101.0 * pulse) as u8;
    let border_g = (150.0 * pulse) as u8;
    let border_b = (243.0 * pulse) as u8;

    let title = if has_pending { " Activity " } else { " Done " };
    let title_color = if has_pending { SAPPHIRE } else { OLIVE };

    let block = Block::default()
        .title(Span::styled(
            title,
            Style::default().fg(title_color).add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(border_r, border_g, border_b)))
        .style(Style::default().bg(glass_bg));

    let inner = block.inner(popup_area);
    frame.render_widget(block, popup_area);

    // Activity entries
    let mut lines: Vec<Line> = Vec::new();

    for activity in app.activity.entries.iter() {
        let (icon, icon_color) = if activity.is_complete {
            ("✓", OLIVE)
        } else {
            (spinner, SAPPHIRE)
        };

        let text_color = if activity.is_complete {
            TEXT_MUTED
        } else {
            TEXT_PRIMARY
        };

        // Truncate message if needed
        let max_msg_len = (popup_width as usize).saturating_sub(6);
        let msg: String = activity.message.chars().take(max_msg_len).collect();
        let msg = if activity.message.len() > max_msg_len {
            format!("{}…", msg)
        } else {
            msg
        };

        lines.push(Line::from(vec![
            Span::styled(format!(" {} ", icon), Style::default().fg(icon_color)),
            Span::styled(msg, Style::default().fg(text_color)),
        ]));
    }

    let activity_list = Paragraph::new(lines);
    frame.render_widget(activity_list, inner);
}

/// Draw the 2D embedding visualization scatter plot
fn draw_visualization(frame: &mut Frame, app: &App, area: Rect) {
    use crate::ui_state::Focus;

    // Border color based on focus
    let border_color = if app.ui.focus == Focus::Visualization {
        SAPPHIRE  // Highlighted when focused
    } else {
        BORDER_DIM
    };

    let block = Block::default()
        .title(Span::styled(
            format!(" Embeddings ({}) ", app.embedding_points.len()),
            Style::default().fg(CYAN_LIGHT).add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    if app.embedding_points.is_empty() {
        // Show empty state message
        let empty_msg = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled("No embeddings loaded", Style::default().fg(TEXT_MUTED))),
            Line::from(""),
            Line::from(Span::styled("Use /init to index codebase", Style::default().fg(TEXT_MUTED))),
        ])
        .alignment(Alignment::Center);
        frame.render_widget(empty_msg, inner);
        return;
    }

    // Create a canvas for the scatter plot
    let plot_width = inner.width as usize;
    let plot_height = inner.height as usize;

    if plot_width == 0 || plot_height == 0 {
        return;
    }

    // Build a 2D grid of characters for the plot
    let mut grid: Vec<Vec<Option<usize>>> = vec![vec![None; plot_width]; plot_height];

    // Map each point to screen coordinates
    for (idx, point) in app.embedding_points.iter().enumerate() {
        // x and y are normalized 0-1, map to screen coordinates
        let screen_x = (point.x * (plot_width - 1) as f64).round() as usize;
        let screen_y = (point.y * (plot_height - 1) as f64).round() as usize;

        // Clamp to bounds
        let sx = screen_x.min(plot_width - 1);
        let sy = screen_y.min(plot_height - 1);

        // Store point index in grid
        grid[sy][sx] = Some(idx);
    }

    // Render the grid as lines
    let mut lines: Vec<Line> = Vec::new();

    for (row_idx, row) in grid.iter().enumerate() {
        let mut spans: Vec<Span> = Vec::new();

        for (col_idx, cell) in row.iter().enumerate() {
            match cell {
                Some(point_idx) => {
                    let is_hovered = app.ui.hovered_point == Some(*point_idx);
                    let point = &app.embedding_points[*point_idx];

                    // Color based on chunk type and hover state
                    let dot_color = if is_hovered {
                        PALE_YELLOW // Highlighted on hover
                    } else {
                        match point.chunk_type.as_str() {
                            "function" | "method" => SAPPHIRE,
                            "class" | "struct" => COPPER,
                            "module" | "import" => CYAN_LIGHT,
                            "comment" | "docstring" => OLIVE,
                            _ => LAVENDER,
                        }
                    };

                    let dot_char = if is_hovered { "◆" } else { "●" };
                    spans.push(Span::styled(dot_char, Style::default().fg(dot_color)));
                }
                None => {
                    // Empty space - show subtle background pattern
                    let show_pattern = (row_idx + col_idx) % 8 == 0;
                    if show_pattern {
                        spans.push(Span::styled("·", Style::default().fg(Color::Rgb(30, 35, 45))));
                    } else {
                        spans.push(Span::raw(" "));
                    }
                }
            }
        }

        lines.push(Line::from(spans));
    }

    let plot = Paragraph::new(lines);
    frame.render_widget(plot, inner);

    // Draw tooltip for hovered point (if any)
    if let Some(idx) = app.ui.hovered_point {
        if let Some(point) = app.embedding_points.get(idx) {
            // Position tooltip near the point
            let tooltip_x = (point.x * (plot_width - 1) as f64).round() as u16;
            let tooltip_y = (point.y * (plot_height - 1) as f64).round() as u16;

            // Create tooltip content
            let tooltip_text = format!(" {} ", point.id);
            let tooltip_width = tooltip_text.len() as u16;

            // Calculate tooltip position (try to avoid going off-screen)
            let tip_x = inner.x + tooltip_x.min(inner.width.saturating_sub(tooltip_width + 2));
            let tip_y = if tooltip_y < inner.height / 2 {
                inner.y + tooltip_y + 1
            } else {
                inner.y + tooltip_y.saturating_sub(1)
            };

            let tooltip_area = Rect {
                x: tip_x,
                y: tip_y,
                width: tooltip_width.min(inner.width),
                height: 1,
            };

            // Draw tooltip background and text
            frame.render_widget(Clear, tooltip_area);
            let tooltip = Paragraph::new(tooltip_text)
                .style(Style::default().fg(BG_DARK).bg(PALE_YELLOW));
            frame.render_widget(tooltip, tooltip_area);
        }
    }

    // Draw legend at the bottom
    let legend_y = inner.y + inner.height.saturating_sub(1);
    if legend_y > inner.y {
        let legend_area = Rect {
            x: inner.x,
            y: legend_y,
            width: inner.width,
            height: 1,
        };

        let legend = Line::from(vec![
            Span::styled("●", Style::default().fg(SAPPHIRE)),
            Span::styled(" fn ", Style::default().fg(TEXT_MUTED)),
            Span::styled("●", Style::default().fg(COPPER)),
            Span::styled(" cls ", Style::default().fg(TEXT_MUTED)),
            Span::styled("●", Style::default().fg(CYAN_LIGHT)),
            Span::styled(" mod ", Style::default().fg(TEXT_MUTED)),
            Span::styled("●", Style::default().fg(OLIVE)),
            Span::styled(" doc ", Style::default().fg(TEXT_MUTED)),
        ]);
        frame.render_widget(Paragraph::new(legend), legend_area);
    }
}
