// Backend communication with Python process via JSON-RPC over stdio

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::thread;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TokenStats {
    #[serde(default)]
    pub total_input: u64,
    #[serde(default)]
    pub total_output: u64,
    #[serde(default)]
    pub total_tokens: u64,
    #[serde(default)]
    pub total_cost: f64,
    #[serde(default)]
    pub request_count: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub budget: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub budget_remaining: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub budget_percentage: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Session {
    pub id: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub codebase_path: Option<String>,
    pub created_at: String,
    pub last_accessed: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RagSearchResult {
    pub id: String,
    pub content: String,
    #[serde(default)]
    pub score: f64,
    #[serde(default)]
    pub relevance: f64,
    #[serde(default)]
    pub metadata: RagChunkMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RagChunkMetadata {
    #[serde(default)]
    pub path: String,
    #[serde(default, rename = "type")]
    pub chunk_type: String,
    #[serde(default)]
    pub language: String,
    #[serde(default)]
    pub signature: String,
    #[serde(default)]
    pub concepts: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagSearchResponse {
    #[serde(default)]
    pub results: Vec<RagSearchResult>,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagIngestResponse {
    #[serde(default)]
    pub ingested: usize,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagStatusResponse {
    #[serde(default)]
    pub initialized: bool,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub db_path: Option<String>,
    #[serde(default)]
    pub collection: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CodebaseInitStats {
    #[serde(default)]
    pub files_scanned: usize,
    #[serde(default)]
    pub units_extracted: usize,
    #[serde(default)]
    pub chunks_generated: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodebaseInitResponse {
    #[serde(default)]
    pub chunks: usize,
    #[serde(default)]
    pub stats: Option<CodebaseInitStats>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub response: String,
    #[serde(default)]
    pub tokens: Option<TokenStats>,
}

#[derive(Debug, Clone, Serialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    method: String,
    params: serde_json::Value,
    id: u64,
}

#[derive(Debug, Clone, Deserialize)]
struct JsonRpcResponse {
    #[allow(dead_code)]
    jsonrpc: String,
    result: Option<serde_json::Value>,
    error: Option<JsonRpcError>,
    id: u64,
}

#[derive(Debug, Clone, Deserialize)]
struct JsonRpcNotification {
    #[allow(dead_code)]
    jsonrpc: String,
    method: String,
    #[allow(dead_code)]
    params: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize)]
struct JsonRpcError {
    code: i32,
    message: String,
    #[allow(dead_code)]
    data: Option<serde_json::Value>,
}

impl JsonRpcRequest {
    fn new(method: &str, params: serde_json::Value, id: u64) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            method: method.to_string(),
            params,
            id,
        }
    }
}

#[derive(Debug)]
pub enum BackendError {
    NotStarted,
    ProcessDied,
    RpcError { code: i32, message: String },
    IoError(String),
    ParseError(String),
}

impl std::fmt::Display for BackendError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BackendError::NotStarted => write!(f, "Backend not started"),
            BackendError::ProcessDied => write!(f, "Backend process died"),
            BackendError::RpcError { code, message } => write!(f, "RPC error {}: {}", code, message),
            BackendError::IoError(e) => write!(f, "IO error: {}", e),
            BackendError::ParseError(e) => write!(f, "Parse error: {}", e),
        }
    }
}

type PendingRequests = Arc<Mutex<HashMap<u64, Sender<Result<serde_json::Value, BackendError>>>>>;

pub struct Backend {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    request_id: u64,
    pending: PendingRequests,
    ready: bool,
}

impl Backend {
    pub fn new() -> Self {
        Self {
            child: None,
            stdin: None,
            request_id: 0,
            pending: Arc::new(Mutex::new(HashMap::new())),
            ready: false,
        }
    }

    pub fn start(&mut self, python_path: Option<&str>) -> Result<(), BackendError> {
        // Use python3 on Unix, python on Windows
        #[cfg(windows)]
        let default_python = "python";
        #[cfg(not(windows))]
        let default_python = "python3";

        let python = python_path.unwrap_or(default_python);

        let mut child = Command::new(python)
            .args(["-m", "openagent", "server"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| BackendError::IoError(e.to_string()))?;

        let stdout = child.stdout.take().ok_or_else(|| {
            BackendError::IoError("Failed to get stdout".to_string())
        })?;

        let stdin = child.stdin.take().ok_or_else(|| {
            BackendError::IoError("Failed to get stdin".to_string())
        })?;

        self.child = Some(child);
        self.stdin = Some(stdin);

        // Spawn reader thread
        let pending = Arc::clone(&self.pending);
        thread::spawn(move || {
            Self::reader_loop(stdout, pending);
        });

        self.ready = true;
        Ok(())
    }

    fn reader_loop(stdout: ChildStdout, pending: PendingRequests) {
        let reader = BufReader::new(stdout);

        for line in reader.lines() {
            let line = match line {
                Ok(l) => l,
                Err(_) => break,
            };

            if line.is_empty() {
                continue;
            }

            // Try to parse as response (has id field)
            if let Ok(response) = serde_json::from_str::<JsonRpcResponse>(&line) {
                let mut pending_guard = pending.lock().unwrap();
                if let Some(sender) = pending_guard.remove(&response.id) {
                    let result = if let Some(error) = response.error {
                        Err(BackendError::RpcError {
                            code: error.code,
                            message: error.message,
                        })
                    } else {
                        Ok(response.result.unwrap_or(serde_json::Value::Null))
                    };
                    let _ = sender.send(result);
                }
            } else if let Ok(_notification) = serde_json::from_str::<JsonRpcNotification>(&line) {
                // Handle notifications (like server.ready)
                // For now we just ignore them, but could emit events
            }
        }
    }

    fn next_id(&mut self) -> u64 {
        self.request_id += 1;
        self.request_id
    }

    fn call(&mut self, method: &str, params: serde_json::Value) -> Result<serde_json::Value, BackendError> {
        if !self.ready {
            return Err(BackendError::NotStarted);
        }

        let id = self.next_id();
        let request = JsonRpcRequest::new(method, params, id);

        // Create channel for response
        let (tx, rx) = mpsc::channel();

        // Register pending request
        {
            let mut pending = self.pending.lock().unwrap();
            pending.insert(id, tx);
        }

        // Send request
        let stdin = self.stdin.as_mut().ok_or(BackendError::NotStarted)?;
        let request_json = serde_json::to_string(&request)
            .map_err(|e| BackendError::ParseError(e.to_string()))?;

        writeln!(stdin, "{}", request_json)
            .map_err(|e| BackendError::IoError(e.to_string()))?;
        stdin.flush()
            .map_err(|e| BackendError::IoError(e.to_string()))?;

        // Wait for response (with timeout)
        rx.recv_timeout(std::time::Duration::from_secs(60))
            .map_err(|_| BackendError::ProcessDied)?
    }

    pub fn chat_send(&mut self, message: &str) -> Result<ChatResponse, BackendError> {
        let params = serde_json::json!({
            "message": message
        });

        let result = self.call("chat.send", params)?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn get_token_stats(&mut self) -> Result<TokenStats, BackendError> {
        let result = self.call("tokens.get", serde_json::json!({}))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn create_session(&mut self, name: Option<&str>, codebase_path: Option<&str>) -> Result<Session, BackendError> {
        let mut params = serde_json::Map::new();
        if let Some(n) = name {
            params.insert("name".to_string(), serde_json::Value::String(n.to_string()));
        }
        if let Some(p) = codebase_path {
            params.insert("codebase_path".to_string(), serde_json::Value::String(p.to_string()));
        }

        let result = self.call("session.create", serde_json::Value::Object(params))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn list_sessions(&mut self, limit: Option<u32>) -> Result<Vec<Session>, BackendError> {
        let params = serde_json::json!({
            "limit": limit.unwrap_or(20)
        });

        let result = self.call("session.list", params)?;

        #[derive(Deserialize)]
        struct SessionList {
            sessions: Vec<Session>,
        }

        let list: SessionList = serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))?;

        Ok(list.sessions)
    }

    pub fn is_running(&self) -> bool {
        self.ready && self.child.is_some()
    }

    pub fn rag_search(&mut self, query: &str, n_results: Option<usize>) -> Result<RagSearchResponse, BackendError> {
        let params = serde_json::json!({
            "query": query,
            "n_results": n_results.unwrap_or(5)
        });

        let result = self.call("rag.search", params)?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn rag_ingest_json(&mut self, json_path: &str) -> Result<RagIngestResponse, BackendError> {
        let params = serde_json::json!({
            "json_path": json_path
        });

        let result = self.call("rag.ingest", params)?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn rag_status(&mut self) -> Result<RagStatusResponse, BackendError> {
        let result = self.call("rag.status", serde_json::json!({}))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn codebase_init(&mut self, path: Option<&str>, clear: bool) -> Result<CodebaseInitResponse, BackendError> {
        let mut params = serde_json::Map::new();
        if let Some(p) = path {
            params.insert("path".to_string(), serde_json::Value::String(p.to_string()));
        }
        if clear {
            params.insert("clear".to_string(), serde_json::Value::Bool(true));
        }

        let result = self.call("codebase.init", serde_json::Value::Object(params))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn stop(&mut self) {
        self.ready = false;
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.stdin = None;
    }
}

impl Default for Backend {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}
