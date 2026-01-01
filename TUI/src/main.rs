mod app;
mod backend;
mod markdown;
mod ui;

use std::env;
use std::io;

use arboard::Clipboard;
use crossterm::{
    event::{self, DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture, Event, KeyCode, KeyModifiers, MouseEventKind, MouseButton},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

use app::App;
use ui::draw;

fn main() -> io::Result<()> {
    // Parse command line args
    let args: Vec<String> = env::args().collect();
    let offline_mode = args.iter().any(|a| a == "--offline" || a == "-o");

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture, EnableBracketedPaste)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Create app state
    let mut app = App::new();

    // Run app
    let result = run_app(&mut terminal, &mut app, offline_mode);

    // Restore terminal
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture,
        DisableBracketedPaste
    )?;
    terminal.show_cursor()?;

    if let Err(e) = result {
        eprintln!("Error: {}", e);
    }

    Ok(())
}

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
    offline_mode: bool,
) -> io::Result<()> {
    loop {
        // Update animation frame
        app.tick();

        terminal.draw(|frame| draw(frame, app))?;

        // Poll for events with timeout (60 FPS for smooth animation)
        if event::poll(std::time::Duration::from_millis(16))? {
            match event::read()? {
                Event::Key(key) => {
                    match app.screen {
                        app::Screen::Home => {
                            // Any key transitions to chat
                            if key.code != KeyCode::Esc {
                                app.screen = app::Screen::Chat;

                                // Start backend when entering chat (unless offline mode)
                                if !offline_mode && !app.backend_connected {
                                    if let Err(e) = app.start_backend() {
                                        app.status_message =
                                            Some(format!("Backend error: {} (running offline)", e));
                                    }
                                }
                            } else {
                                return Ok(());
                            }
                        }
                        app::Screen::Chat => match key.code {
                            KeyCode::Esc => {
                                if app.showing_command_popup() {
                                    app.reset_command_selection();
                                } else if app.input.is_empty() {
                                    return Ok(());
                                } else {
                                    app.input.clear();
                                }
                            }
                            KeyCode::Enter => {
                                if app.showing_command_popup() && app.command_selection.is_some() {
                                    app.apply_command_selection();
                                } else {
                                    app.submit_message();
                                }
                            }
                            KeyCode::Tab => {
                                if app.showing_command_popup() && app.command_selection.is_some() {
                                    // Tab applies command selection when popup is showing
                                    app.apply_command_selection();
                                } else if key.modifiers.contains(KeyModifiers::SHIFT) {
                                    // Shift+Tab cycles focus between panels
                                    app.cycle_focus();
                                } else {
                                    // Tab toggles visualization panel
                                    app.toggle_visualization();
                                }
                            }
                            KeyCode::Backspace => {
                                app.input.pop();
                                app.reset_command_selection();
                            }
                            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                                return Ok(());
                            }
                            KeyCode::Char('v') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                                // Ctrl+V: Get clipboard content
                                if let Ok(mut clipboard) = Clipboard::new() {
                                    if let Ok(text) = clipboard.get_text() {
                                        // Filter newlines for input
                                        let filtered: String = text.chars()
                                            .filter(|c| *c != '\r')
                                            .map(|c| if c == '\n' { ' ' } else { c })
                                            .collect();
                                        app.input.push_str(&filtered);
                                        app.reset_command_selection();
                                    }
                                }
                            }
                            KeyCode::Char(c) => {
                                app.input.push(c);
                                app.reset_command_selection();
                            }
                            KeyCode::Up => {
                                if app.showing_command_popup() {
                                    app.command_select_up();
                                } else {
                                    app.scroll_up();
                                }
                            }
                            KeyCode::Down => {
                                if app.showing_command_popup() {
                                    app.command_select_down();
                                } else {
                                    app.scroll_down();
                                }
                            }
                            KeyCode::F(2) => {
                                // F2: Toggle markdown raw/preview mode
                                app.toggle_markdown_mode();
                            }
                            _ => {}
                        },
                    }
                }
                Event::Paste(text) => {
                    // Handle paste event (bracketed paste mode)
                    if app.screen == app::Screen::Chat {
                        // Filter out newlines for single-line input, or keep for multi-line
                        let filtered: String = text.chars()
                            .filter(|c| *c != '\r')
                            .map(|c| if c == '\n' { ' ' } else { c })
                            .collect();
                        app.input.push_str(&filtered);
                        app.reset_command_selection();
                    }
                }
                Event::Mouse(mouse) => {
                    if app.screen == app::Screen::Chat {
                        let term_size = terminal.size()?;
                        let term_height = term_size.height;
                        let term_width = term_size.width;
                        // Input box is at the bottom (last 3 rows roughly)
                        let input_area_start = term_height.saturating_sub(5);

                        // Calculate visualization area boundaries (when visible)
                        // Layout: 1px padding, 26px sidebar, 1px gap, remaining split 50/50
                        let sidebar_end = 28; // 1 + 26 + 1
                        let chat_area_width = term_width.saturating_sub(sidebar_end + 2);
                        let viz_start = if app.show_visualization {
                            sidebar_end + (chat_area_width / 2) + 1
                        } else {
                            term_width // Off-screen when not visible
                        };

                        match mouse.kind {
                            MouseEventKind::Down(MouseButton::Left) => {
                                // Click to focus
                                if mouse.row >= input_area_start {
                                    app.focus = app::Focus::Input;
                                } else if app.show_visualization && mouse.column >= viz_start {
                                    app.focus = app::Focus::Visualization;
                                } else if mouse.column > sidebar_end {
                                    app.focus = app::Focus::Chat;
                                }
                            }
                            MouseEventKind::ScrollUp => {
                                // Scroll up in chat area
                                if mouse.column > sidebar_end && mouse.row < input_area_start && mouse.column < viz_start {
                                    app.scroll_up();
                                }
                            }
                            MouseEventKind::ScrollDown => {
                                // Scroll down in chat area
                                if mouse.column > sidebar_end && mouse.row < input_area_start && mouse.column < viz_start {
                                    app.scroll_down();
                                }
                            }
                            MouseEventKind::Moved => {
                                // Handle hover in visualization area
                                if app.show_visualization && mouse.column >= viz_start && mouse.row < input_area_start {
                                    // Calculate inner area (accounting for borders)
                                    let viz_width = term_width.saturating_sub(viz_start + 2) as f64;
                                    let viz_height = input_area_start.saturating_sub(4) as f64;
                                    let viz_inner_x = (viz_start + 1) as f64;
                                    let viz_inner_y = 2.0; // After top padding and border

                                    if viz_width > 0.0 && viz_height > 0.0 {
                                        // Convert mouse position to normalized 0-1 coordinates
                                        let norm_x = ((mouse.column as f64) - viz_inner_x) / viz_width;
                                        let norm_y = ((mouse.row as f64) - viz_inner_y) / viz_height;

                                        // Find point near cursor (with tolerance)
                                        let tolerance = 0.05; // 5% of view
                                        app.hovered_point = app.find_point_at(norm_x, norm_y, tolerance);
                                    } else {
                                        app.hovered_point = None;
                                    }
                                } else {
                                    app.hovered_point = None;
                                }
                            }
                            _ => {}
                        }
                    }
                }
                _ => {}
            }
        }
    }
}
