mod app;
mod backend;
mod ui;

use std::env;
use std::io;

use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyModifiers},
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
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
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
        DisableMouseCapture
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
            if let Event::Key(key) = event::read()? {
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
                            // Tab also applies command selection
                            if app.showing_command_popup() && app.command_selection.is_some() {
                                app.apply_command_selection();
                            }
                        }
                        KeyCode::Backspace => {
                            app.input.pop();
                            app.reset_command_selection();
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            return Ok(());
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
                        _ => {}
                    },
                }
            }
        }
    }
}
