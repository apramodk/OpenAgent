//! Markdown parsing and rendering for TUI display.
//!
//! Converts markdown text to styled ratatui Spans for terminal display.

use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

/// Colors for markdown elements
const CODE_BG: Color = Color::Rgb(40, 44, 52);
const CODE_FG: Color = Color::Rgb(171, 178, 191);
const HEADING_COLOR: Color = Color::Rgb(97, 175, 239);
const BOLD_COLOR: Color = Color::Rgb(224, 208, 183);
const ITALIC_COLOR: Color = Color::Rgb(152, 195, 121);
const LINK_COLOR: Color = Color::Rgb(86, 182, 194);
const LIST_BULLET_COLOR: Color = Color::Rgb(198, 120, 221);
const BLOCKQUOTE_COLOR: Color = Color::Rgb(128, 128, 128);

/// Parsed markdown element
#[derive(Debug, Clone, PartialEq)]
pub enum MarkdownElement {
    Text(String),
    Bold(String),
    Italic(String),
    BoldItalic(String),
    Code(String),
    CodeBlock { language: Option<String>, code: String },
    Heading { level: u8, text: String },
    Link { text: String, url: String },
    ListItem { indent: usize, text: String },
    BlockQuote(String),
    HorizontalRule,
    Newline,
}

/// Parse markdown text into elements
pub fn parse_markdown(text: &str) -> Vec<MarkdownElement> {
    let mut elements = Vec::new();
    let mut in_code_block = false;
    let mut code_block_lang: Option<String> = None;
    let mut code_block_content = String::new();

    for line in text.lines() {
        // Handle code blocks
        if line.starts_with("```") {
            if in_code_block {
                // End code block
                elements.push(MarkdownElement::CodeBlock {
                    language: code_block_lang.take(),
                    code: code_block_content.trim_end().to_string(),
                });
                code_block_content.clear();
                in_code_block = false;
            } else {
                // Start code block
                in_code_block = true;
                let lang = line.trim_start_matches('`').trim();
                code_block_lang = if lang.is_empty() { None } else { Some(lang.to_string()) };
            }
            continue;
        }

        if in_code_block {
            if !code_block_content.is_empty() {
                code_block_content.push('\n');
            }
            code_block_content.push_str(line);
            continue;
        }

        // Horizontal rule
        if line.trim() == "---" || line.trim() == "***" || line.trim() == "___" {
            elements.push(MarkdownElement::HorizontalRule);
            continue;
        }

        // Headings
        if let Some(heading) = parse_heading(line) {
            elements.push(heading);
            continue;
        }

        // Block quotes
        if line.starts_with('>') {
            let text = line.trim_start_matches('>').trim().to_string();
            elements.push(MarkdownElement::BlockQuote(text));
            continue;
        }

        // List items
        if let Some(list_item) = parse_list_item(line) {
            elements.push(list_item);
            continue;
        }

        // Empty line
        if line.trim().is_empty() {
            elements.push(MarkdownElement::Newline);
            continue;
        }

        // Parse inline elements
        parse_inline_elements(line, &mut elements);
        elements.push(MarkdownElement::Newline);
    }

    // Handle unclosed code block
    if in_code_block && !code_block_content.is_empty() {
        elements.push(MarkdownElement::CodeBlock {
            language: code_block_lang,
            code: code_block_content,
        });
    }

    elements
}

fn parse_heading(line: &str) -> Option<MarkdownElement> {
    let trimmed = line.trim_start();
    if trimmed.starts_with('#') {
        let level = trimmed.chars().take_while(|c| *c == '#').count() as u8;
        if level <= 6 {
            let text = trimmed.trim_start_matches('#').trim().to_string();
            return Some(MarkdownElement::Heading { level, text });
        }
    }
    None
}

fn parse_list_item(line: &str) -> Option<MarkdownElement> {
    let indent = line.len() - line.trim_start().len();
    let trimmed = line.trim_start();

    // Unordered list: -, *, +
    if trimmed.starts_with("- ") || trimmed.starts_with("* ") || trimmed.starts_with("+ ") {
        let text = trimmed[2..].to_string();
        return Some(MarkdownElement::ListItem { indent, text });
    }

    // Ordered list: 1. 2. etc
    if let Some(pos) = trimmed.find(". ") {
        let prefix = &trimmed[..pos];
        if prefix.chars().all(|c| c.is_ascii_digit()) {
            let text = trimmed[pos + 2..].to_string();
            return Some(MarkdownElement::ListItem { indent, text });
        }
    }

    None
}

fn parse_inline_elements(line: &str, elements: &mut Vec<MarkdownElement>) {
    let mut chars = line.chars().peekable();
    let mut current_text = String::new();

    // Helper to check if a char is a word character (alphanumeric)
    fn is_word_char(c: char) -> bool {
        c.is_alphanumeric()
    }

    while let Some(c) = chars.next() {
        match c {
            '`' => {
                // Inline code
                if !current_text.is_empty() {
                    elements.push(MarkdownElement::Text(current_text.clone()));
                    current_text.clear();
                }
                let mut code = String::new();
                while let Some(&next) = chars.peek() {
                    if next == '`' {
                        chars.next();
                        break;
                    }
                    code.push(chars.next().unwrap());
                }
                if !code.is_empty() {
                    elements.push(MarkdownElement::Code(code));
                }
            }
            '*' | '_' => {
                let marker = c;

                // For underscores, check if preceded by word char - if so, treat as literal
                if marker == '_' && current_text.chars().last().map_or(false, is_word_char) {
                    current_text.push(c);
                    continue;
                }

                // Check for bold/italic
                let is_double = chars.peek() == Some(&marker);

                if is_double {
                    chars.next(); // consume second marker

                    // Check for triple (bold italic)
                    let is_triple = chars.peek() == Some(&marker);
                    if is_triple {
                        chars.next();
                    }

                    if !current_text.is_empty() {
                        elements.push(MarkdownElement::Text(current_text.clone()));
                        current_text.clear();
                    }

                    let mut content = String::new();
                    let end_count = if is_triple { 3 } else { 2 };
                    let mut found_end = false;

                    while let Some(next) = chars.next() {
                        if next == marker {
                            // For underscores, check word boundary before treating as end marker
                            if marker == '_' && content.chars().last().map_or(false, is_word_char)
                                && chars.peek().map_or(false, |&c| is_word_char(c))
                            {
                                content.push(next);
                                continue;
                            }

                            let mut count = 1;
                            while chars.peek() == Some(&marker) && count < end_count {
                                chars.next();
                                count += 1;
                            }
                            if count >= end_count {
                                found_end = true;
                                break;
                            }
                            for _ in 0..count {
                                content.push(marker);
                            }
                        } else {
                            content.push(next);
                        }
                    }

                    if found_end && !content.is_empty() {
                        if is_triple {
                            elements.push(MarkdownElement::BoldItalic(content));
                        } else {
                            elements.push(MarkdownElement::Bold(content));
                        }
                    } else {
                        current_text.push(marker);
                        current_text.push(marker);
                        if is_triple {
                            current_text.push(marker);
                        }
                        current_text.push_str(&content);
                    }
                } else {
                    // Single marker - italic
                    // For underscores, peek ahead to validate it's not inside a word
                    if marker == '_' {
                        let next_is_word = chars.peek().map_or(false, |&c| is_word_char(c));
                        if !next_is_word {
                            // Just a standalone underscore, treat as text
                            current_text.push(c);
                            continue;
                        }
                    }

                    if !current_text.is_empty() {
                        elements.push(MarkdownElement::Text(current_text.clone()));
                        current_text.clear();
                    }

                    let mut content = String::new();
                    let mut found_end = false;

                    while let Some(next) = chars.next() {
                        if next == marker {
                            // For underscores, verify word boundary
                            if marker == '_' && content.chars().last().map_or(false, is_word_char)
                                && chars.peek().map_or(false, |&c| is_word_char(c))
                            {
                                // Underscore inside word, not an end marker
                                content.push(next);
                                continue;
                            }
                            found_end = true;
                            break;
                        }
                        content.push(next);
                    }

                    if found_end && !content.is_empty() {
                        elements.push(MarkdownElement::Italic(content));
                    } else {
                        current_text.push(marker);
                        current_text.push_str(&content);
                    }
                }
            }
            '[' => {
                // Link: [text](url)
                if !current_text.is_empty() {
                    elements.push(MarkdownElement::Text(current_text.clone()));
                    current_text.clear();
                }

                let mut link_text = String::new();
                let mut found_bracket = false;

                while let Some(next) = chars.next() {
                    if next == ']' {
                        found_bracket = true;
                        break;
                    }
                    link_text.push(next);
                }

                if found_bracket && chars.peek() == Some(&'(') {
                    chars.next(); // consume '('
                    let mut url = String::new();
                    let mut found_paren = false;

                    while let Some(next) = chars.next() {
                        if next == ')' {
                            found_paren = true;
                            break;
                        }
                        url.push(next);
                    }

                    if found_paren {
                        elements.push(MarkdownElement::Link { text: link_text, url });
                    } else {
                        current_text.push('[');
                        current_text.push_str(&link_text);
                        current_text.push_str("](");
                        current_text.push_str(&url);
                    }
                } else {
                    current_text.push('[');
                    current_text.push_str(&link_text);
                    if found_bracket {
                        current_text.push(']');
                    }
                }
            }
            _ => {
                current_text.push(c);
            }
        }
    }

    if !current_text.is_empty() {
        elements.push(MarkdownElement::Text(current_text));
    }
}

/// Render markdown elements to styled ratatui Lines
pub fn render_markdown(elements: &[MarkdownElement], width: usize) -> Vec<Line<'static>> {
    let mut lines: Vec<Line<'static>> = Vec::new();

    for element in elements {
        match element {
            MarkdownElement::Text(text) => {
                append_spans_to_lines(&mut lines, vec![Span::raw(text.clone())], width);
            }
            MarkdownElement::Bold(text) => {
                let span = Span::styled(
                    text.clone(),
                    Style::default().fg(BOLD_COLOR).add_modifier(Modifier::BOLD),
                );
                append_spans_to_lines(&mut lines, vec![span], width);
            }
            MarkdownElement::Italic(text) => {
                let span = Span::styled(
                    text.clone(),
                    Style::default().fg(ITALIC_COLOR).add_modifier(Modifier::ITALIC),
                );
                append_spans_to_lines(&mut lines, vec![span], width);
            }
            MarkdownElement::BoldItalic(text) => {
                let span = Span::styled(
                    text.clone(),
                    Style::default()
                        .fg(BOLD_COLOR)
                        .add_modifier(Modifier::BOLD | Modifier::ITALIC),
                );
                append_spans_to_lines(&mut lines, vec![span], width);
            }
            MarkdownElement::Code(code) => {
                let span = Span::styled(
                    format!(" {} ", code),
                    Style::default().fg(CODE_FG).bg(CODE_BG),
                );
                append_spans_to_lines(&mut lines, vec![span], width);
            }
            MarkdownElement::CodeBlock { language, code } => {
                // Header line with language
                let lang_text = language.as_deref().unwrap_or("code");
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("┌─ {} ", lang_text),
                        Style::default().fg(CODE_FG),
                    ),
                    Span::styled(
                        "─".repeat(width.saturating_sub(lang_text.len() + 4)),
                        Style::default().fg(Color::Rgb(60, 60, 60)),
                    ),
                ]));

                // Code lines
                for code_line in code.lines() {
                    lines.push(Line::from(vec![
                        Span::styled("│ ", Style::default().fg(Color::Rgb(60, 60, 60))),
                        Span::styled(
                            code_line.to_string(),
                            Style::default().fg(CODE_FG).bg(CODE_BG),
                        ),
                    ]));
                }

                // Footer line
                lines.push(Line::from(Span::styled(
                    format!("└{}┘", "─".repeat(width.saturating_sub(2))),
                    Style::default().fg(Color::Rgb(60, 60, 60)),
                )));
            }
            MarkdownElement::Heading { level, text } => {
                // Style headings without showing # - use different emphasis per level
                let style = match level {
                    1 => Style::default()
                        .fg(HEADING_COLOR)
                        .add_modifier(Modifier::BOLD | Modifier::UNDERLINED),
                    2 => Style::default()
                        .fg(HEADING_COLOR)
                        .add_modifier(Modifier::BOLD),
                    _ => Style::default()
                        .fg(HEADING_COLOR)
                        .add_modifier(Modifier::BOLD | Modifier::DIM),
                };
                // Add visual separator for h1
                if *level == 1 {
                    lines.push(Line::from(Span::styled(
                        text.clone(),
                        style,
                    )));
                    lines.push(Line::from(Span::styled(
                        "─".repeat(text.len().min(width)),
                        Style::default().fg(Color::Rgb(70, 85, 110)),
                    )));
                } else {
                    lines.push(Line::from(Span::styled(text.clone(), style)));
                }
            }
            MarkdownElement::Link { text, url: _ } => {
                // In terminal, we just show the text styled as a link
                let span = Span::styled(
                    text.clone(),
                    Style::default()
                        .fg(LINK_COLOR)
                        .add_modifier(Modifier::UNDERLINED),
                );
                append_spans_to_lines(&mut lines, vec![span], width);
            }
            MarkdownElement::ListItem { indent, text } => {
                let indent_str = " ".repeat(*indent);
                lines.push(Line::from(vec![
                    Span::raw(indent_str),
                    Span::styled("• ", Style::default().fg(LIST_BULLET_COLOR)),
                    Span::raw(text.clone()),
                ]));
            }
            MarkdownElement::BlockQuote(text) => {
                lines.push(Line::from(vec![
                    Span::styled("│ ", Style::default().fg(BLOCKQUOTE_COLOR)),
                    Span::styled(
                        text.clone(),
                        Style::default()
                            .fg(BLOCKQUOTE_COLOR)
                            .add_modifier(Modifier::ITALIC),
                    ),
                ]));
            }
            MarkdownElement::HorizontalRule => {
                lines.push(Line::from(Span::styled(
                    "─".repeat(width),
                    Style::default().fg(Color::Rgb(80, 80, 80)),
                )));
            }
            MarkdownElement::Newline => {
                // Empty line or start new line
                if lines.is_empty() || !lines.last().map_or(true, |l| l.spans.is_empty()) {
                    lines.push(Line::from(""));
                }
            }
        }
    }

    lines
}

fn append_spans_to_lines(lines: &mut Vec<Line<'static>>, spans: Vec<Span<'static>>, _width: usize) {
    if lines.is_empty() {
        lines.push(Line::from(spans));
    } else {
        // Append to last line
        let last = lines.last_mut().unwrap();
        last.spans.extend(spans);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_plain_text() {
        let elements = parse_markdown("Hello world");
        assert_eq!(elements.len(), 2); // Text + Newline
        assert!(matches!(&elements[0], MarkdownElement::Text(t) if t == "Hello world"));
    }

    #[test]
    fn test_parse_heading() {
        let elements = parse_markdown("# Heading 1");
        assert!(matches!(&elements[0], MarkdownElement::Heading { level: 1, text } if text == "Heading 1"));

        let elements = parse_markdown("### Heading 3");
        assert!(matches!(&elements[0], MarkdownElement::Heading { level: 3, text } if text == "Heading 3"));
    }

    #[test]
    fn test_parse_bold() {
        let elements = parse_markdown("This is **bold** text");
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Bold(t) if t == "bold")));
    }

    #[test]
    fn test_parse_italic() {
        let elements = parse_markdown("This is *italic* text");
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Italic(t) if t == "italic")));
    }

    #[test]
    fn test_parse_inline_code() {
        let elements = parse_markdown("Use `code` here");
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Code(t) if t == "code")));
    }

    #[test]
    fn test_parse_code_block() {
        let md = "```rust\nfn main() {}\n```";
        let elements = parse_markdown(md);
        assert!(elements.iter().any(|e| matches!(
            e,
            MarkdownElement::CodeBlock { language: Some(lang), code }
            if lang == "rust" && code.contains("fn main()")
        )));
    }

    #[test]
    fn test_parse_code_block_no_language() {
        let md = "```\nsome code\n```";
        let elements = parse_markdown(md);
        assert!(elements.iter().any(|e| matches!(
            e,
            MarkdownElement::CodeBlock { language: None, code }
            if code == "some code"
        )));
    }

    #[test]
    fn test_parse_link() {
        let elements = parse_markdown("Check [this link](https://example.com)");
        assert!(elements.iter().any(|e| matches!(
            e,
            MarkdownElement::Link { text, url }
            if text == "this link" && url == "https://example.com"
        )));
    }

    #[test]
    fn test_parse_unordered_list() {
        let elements = parse_markdown("- Item 1\n- Item 2");
        let list_items: Vec<_> = elements.iter()
            .filter(|e| matches!(e, MarkdownElement::ListItem { .. }))
            .collect();
        assert_eq!(list_items.len(), 2);
    }

    #[test]
    fn test_parse_ordered_list() {
        let elements = parse_markdown("1. First\n2. Second");
        let list_items: Vec<_> = elements.iter()
            .filter(|e| matches!(e, MarkdownElement::ListItem { .. }))
            .collect();
        assert_eq!(list_items.len(), 2);
    }

    #[test]
    fn test_parse_blockquote() {
        let elements = parse_markdown("> This is a quote");
        assert!(elements.iter().any(|e| matches!(
            e,
            MarkdownElement::BlockQuote(t) if t == "This is a quote"
        )));
    }

    #[test]
    fn test_parse_horizontal_rule() {
        for rule in &["---", "***", "___"] {
            let elements = parse_markdown(rule);
            assert!(elements.iter().any(|e| matches!(e, MarkdownElement::HorizontalRule)));
        }
    }

    #[test]
    fn test_render_heading_styled_without_prefix() {
        let elements = vec![MarkdownElement::Heading { level: 2, text: "Test".to_string() }];
        let lines = render_markdown(&elements, 80);
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.content.to_string()).collect();
        // Headings render just the text, not the # prefix
        assert_eq!(text, "Test");
    }

    #[test]
    fn test_render_h1_has_underline() {
        let elements = vec![MarkdownElement::Heading { level: 1, text: "Title".to_string() }];
        let lines = render_markdown(&elements, 80);
        // H1 should have heading text + underline
        assert_eq!(lines.len(), 2);
        let text: String = lines[0].spans.iter().map(|s| s.content.to_string()).collect();
        assert_eq!(text, "Title");
        // Second line should be underline
        let underline: String = lines[1].spans.iter().map(|s| s.content.to_string()).collect();
        assert!(underline.contains("─"));
    }

    #[test]
    fn test_render_code_block_has_border() {
        let elements = vec![MarkdownElement::CodeBlock {
            language: Some("rust".to_string()),
            code: "let x = 1;".to_string(),
        }];
        let lines = render_markdown(&elements, 40);
        assert!(lines.len() >= 3); // header, code, footer

        // Check header contains language
        let header: String = lines[0].spans.iter().map(|s| s.content.to_string()).collect();
        assert!(header.contains("rust"));
    }

    #[test]
    fn test_render_list_has_bullet() {
        let elements = vec![MarkdownElement::ListItem {
            indent: 0,
            text: "Item".to_string(),
        }];
        let lines = render_markdown(&elements, 80);
        let text: String = lines[0].spans.iter().map(|s| s.content.to_string()).collect();
        assert!(text.contains("•"));
    }

    #[test]
    fn test_consecutive_decorators() {
        // Test that consecutive decorators are parsed correctly
        let elements = parse_markdown("**bold** *italic*");
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        let italic_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count();
        assert_eq!(bold_count, 1, "Should have one bold element");
        assert_eq!(italic_count, 1, "Should have one italic element");
    }

    #[test]
    fn test_adjacent_decorators_no_space() {
        // Test decorators directly adjacent
        let elements = parse_markdown("**bold***italic*");
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        let italic_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count();
        assert_eq!(bold_count, 1, "Should have one bold element");
        assert_eq!(italic_count, 1, "Should have one italic element");
    }

    #[test]
    fn test_underscore_decorators() {
        // Test underscore-style decorators
        let elements = parse_markdown("__bold__ _italic_");
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        let italic_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count();
        assert_eq!(bold_count, 1, "Should have one bold element");
        assert_eq!(italic_count, 1, "Should have one italic element");
    }

    #[test]
    fn test_mixed_asterisk_underscore() {
        // Test mixing asterisk and underscore
        let elements = parse_markdown("**bold** _italic_");
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        let italic_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count();
        assert_eq!(bold_count, 1, "Should have one bold element");
        assert_eq!(italic_count, 1, "Should have one italic element");
    }

    #[test]
    fn test_multiple_bolds() {
        let elements = parse_markdown("**first** and **second**");
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        assert_eq!(bold_count, 2, "Should have two bold elements");
    }

    #[test]
    fn test_inline_code_followed_by_bold() {
        let elements = parse_markdown("`code` **bold**");
        let code_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Code(_))).count();
        let bold_count = elements.iter().filter(|e| matches!(e, MarkdownElement::Bold(_))).count();
        assert_eq!(code_count, 1, "Should have one code element");
        assert_eq!(bold_count, 1, "Should have one bold element");
    }

    #[test]
    fn test_underscore_in_word() {
        // Underscores in the middle of words should NOT be treated as decorators
        // This is standard Markdown behavior (e.g., snake_case_variable)
        let elements = parse_markdown("snake_case_variable");
        assert_eq!(
            elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count(),
            0,
            "Underscores inside words should not create italics"
        );
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Text(t) if t == "snake_case_variable")));
    }

    #[test]
    fn test_underscore_word_boundary_still_works() {
        // Underscores at word boundaries should still work for italic
        let elements = parse_markdown("this is _italic_ text");
        assert_eq!(
            elements.iter().filter(|e| matches!(e, MarkdownElement::Italic(_))).count(),
            1,
            "Underscores at word boundaries should create italics"
        );
    }

    #[test]
    fn test_complex_markdown() {
        let md = r#"# Title

This is **bold** and *italic* text.

```python
def hello():
    print("world")
```

- Item 1
- Item 2

> A quote

Check [link](https://example.com).
"#;
        let elements = parse_markdown(md);

        // Should have various element types
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Heading { .. })));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Bold(_))));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Italic(_))));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::CodeBlock { .. })));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::ListItem { .. })));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::BlockQuote(_))));
        assert!(elements.iter().any(|e| matches!(e, MarkdownElement::Link { .. })));
    }
}
