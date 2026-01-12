use crate::action::Action;

pub struct CommandParser;

impl CommandParser {
    pub fn parse(input: &str) -> Result<Action, String> {
        let input = input.trim();
        if !input.starts_with('/') {
            return Err("Not a command".to_string());
        }

        let (cmd, args) = input.split_once(' ').unwrap_or((input, ""));
        let args = args.trim();

        match cmd {
            "/help" => Ok(Action::Help),
            "/clear" => Ok(Action::ClearHistory),
            "/init" => {
                let clear = args == "--clear" || args == "-c";
                Ok(Action::InitCodebase { clear })
            }
            "/rag" => Ok(Action::ShowRagStatus),
            "/search" => {
                if args.is_empty() {
                    Err("Usage: /search <query>\n  Example: /search authentication middleware".to_string())
                } else {
                    Ok(Action::Search { query: args.to_string() })
                }
            }
            "/ingest" => {
                 if args.is_empty() {
                    Err("Usage: /ingest <json_path>\n  Example: /ingest ./specs/codebase.json".to_string())
                } else {
                    Ok(Action::Ingest { path: args.to_string() })
                }
            }
            "/session" => Ok(Action::ShowSessionInfo),
            "/model" => {
                if args.is_empty() {
                    Ok(Action::Model { id: None })
                } else {
                    Ok(Action::Model { id: Some(args.to_string()) })
                }
            }
            "/budget" => Ok(Action::ShowBudget),
            "/debug" => Ok(Action::ToggleDebug),
            "/copy" => Ok(Action::ExportChat),
            "/quit" => Ok(Action::Quit),
            _ => Err(format!("Unknown command: {}. Type /help for available commands.", cmd)),
        }
    }
}
