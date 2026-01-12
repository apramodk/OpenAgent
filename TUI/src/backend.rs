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

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EmbeddingPoint {
    pub id: String,
    pub x: f64,
    pub y: f64,
    #[serde(default)]
    pub path: String,
    #[serde(default, rename = "type")]
    pub chunk_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagEmbeddingsResponse {
    #[serde(default)]
    pub points: Vec<EmbeddingPoint>,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub error: Option<String>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelInfo {
    pub id: String,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelGetResponse {
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelSetResponse {
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub previous: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelListResponse {
    #[serde(default)]
    pub models: Vec<ModelInfo>,
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

/// Stream event from the backend
#[derive(Debug, Clone)]
pub enum StreamEvent {
    Chunk(String),
    Done { tokens: Option<TokenStats> },
}

type StreamSender = Arc<Mutex<Option<Sender<StreamEvent>>>>;

pub struct Backend {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    request_id: u64,
    pending: PendingRequests,
    ready: bool,
    stream_sender: StreamSender,
}

impl Backend {
    pub fn new() -> Self {
        Self {
            child: None,
            stdin: None,
            request_id: 0,
            pending: Arc::new(Mutex::new(HashMap::new())),
            ready: false,
            stream_sender: Arc::new(Mutex::new(None)),
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
        let stream_sender = Arc::clone(&self.stream_sender);
        thread::spawn(move || {
            Self::reader_loop(stdout, pending, stream_sender);
        });

        self.ready = true;
        Ok(())
    }

    fn reader_loop(stdout: ChildStdout, pending: PendingRequests, stream_sender: StreamSender) {
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
            } else if let Ok(notification) = serde_json::from_str::<JsonRpcNotification>(&line) {
                // Handle streaming notifications
                if notification.method == "chat.stream" {
                    if let Some(params) = notification.params {
                        let sender_guard = stream_sender.lock().unwrap();
                        if let Some(sender) = sender_guard.as_ref() {
                            if let Some(chunk) = params.get("chunk").and_then(|v| v.as_str()) {
                                let _ = sender.send(StreamEvent::Chunk(chunk.to_string()));
                            }
                            if params.get("done").and_then(|v| v.as_bool()).unwrap_or(false) {
                                // Parse token stats from done notification
                                let tokens = params.get("tokens")
                                    .and_then(|v| serde_json::from_value::<TokenStats>(v.clone()).ok());
                                let _ = sender.send(StreamEvent::Done { tokens });
                            }
                        }
                    }
                }
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

    /// Start a streaming chat request. Returns a receiver for stream events.
    /// The final response will be returned when you call chat_send_finish().
    pub fn chat_send_stream(&mut self, message: &str) -> Result<mpsc::Receiver<StreamEvent>, BackendError> {
        // Set up stream receiver
        let (tx, rx) = mpsc::channel();
        {
            let mut sender = self.stream_sender.lock().unwrap();
            *sender = Some(tx);
        }

        // Send the request (with streaming enabled)
        let params = serde_json::json!({
            "message": message,
            "stream": true
        });

        // Send request but don't wait for response yet
        if !self.ready {
            return Err(BackendError::NotStarted);
        }

        let id = self.next_id();
        let request = JsonRpcRequest::new("chat.send", params, id);

        // Create channel for final response
        let (resp_tx, _resp_rx) = mpsc::channel();
        {
            let mut pending = self.pending.lock().unwrap();
            pending.insert(id, resp_tx);
        }

        // Send request
        let stdin = self.stdin.as_mut().ok_or(BackendError::NotStarted)?;
        let request_json = serde_json::to_string(&request)
            .map_err(|e| BackendError::ParseError(e.to_string()))?;

        writeln!(stdin, "{}", request_json)
            .map_err(|e| BackendError::IoError(e.to_string()))?;
        stdin.flush()
            .map_err(|e| BackendError::IoError(e.to_string()))?;

        Ok(rx)
    }

    /// Non-streaming chat send (for backwards compatibility)
    pub fn chat_send(&mut self, message: &str) -> Result<ChatResponse, BackendError> {
        let params = serde_json::json!({
            "message": message,
            "stream": false
        });

        let result = self.call("chat.send", params)?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    /// Clear the stream sender (call after streaming is done)
    pub fn clear_stream(&mut self) {
        let mut sender = self.stream_sender.lock().unwrap();
        *sender = None;
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

    pub fn rag_embeddings(&mut self) -> Result<RagEmbeddingsResponse, BackendError> {
        let result = self.call("rag.embeddings", serde_json::json!({}))?;
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

    pub fn model_get(&mut self) -> Result<ModelGetResponse, BackendError> {
        let result = self.call("model.get", serde_json::json!({}))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn model_set(&mut self, model: &str) -> Result<ModelSetResponse, BackendError> {
        let result = self.call("model.set", serde_json::json!({"model": model}))?;
        serde_json::from_value(result)
            .map_err(|e| BackendError::ParseError(e.to_string()))
    }

    pub fn model_list(&mut self) -> Result<ModelListResponse, BackendError> {
        let result = self.call("model.list", serde_json::json!({}))?;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_token_stats_deserialize() {
        let json = r#"{
            "total_input": 100,
            "total_output": 200,
            "total_tokens": 300,
            "total_cost": 0.005,
            "request_count": 5
        }"#;

        let stats: TokenStats = serde_json::from_str(json).unwrap();

        assert_eq!(stats.total_input, 100);
        assert_eq!(stats.total_output, 200);
        assert_eq!(stats.total_tokens, 300);
        assert!((stats.total_cost - 0.005).abs() < 0.0001);
        assert_eq!(stats.request_count, 5);
    }

    #[test]
    fn test_token_stats_deserialize_with_budget() {
        let json = r#"{
            "total_input": 100,
            "total_output": 200,
            "total_tokens": 300,
            "total_cost": 0.005,
            "request_count": 5,
            "budget": 10000,
            "budget_remaining": 9700
        }"#;

        let stats: TokenStats = serde_json::from_str(json).unwrap();

        assert_eq!(stats.budget, Some(10000));
        assert_eq!(stats.budget_remaining, Some(9700));
    }

    #[test]
    fn test_token_stats_deserialize_defaults() {
        let json = r#"{}"#;

        let stats: TokenStats = serde_json::from_str(json).unwrap();

        assert_eq!(stats.total_input, 0);
        assert_eq!(stats.total_output, 0);
        assert_eq!(stats.total_tokens, 0);
        assert_eq!(stats.total_cost, 0.0);
        assert_eq!(stats.budget, None);
    }

    #[test]
    fn test_embedding_point_deserialize() {
        let json = r#"{
            "id": "chunk_123",
            "x": 0.5,
            "y": 0.75,
            "path": "src/main.rs",
            "type": "function"
        }"#;

        let point: EmbeddingPoint = serde_json::from_str(json).unwrap();

        assert_eq!(point.id, "chunk_123");
        assert!((point.x - 0.5).abs() < 0.0001);
        assert!((point.y - 0.75).abs() < 0.0001);
        assert_eq!(point.path, "src/main.rs");
        assert_eq!(point.chunk_type, "function");
    }

    #[test]
    fn test_embedding_point_deserialize_defaults() {
        let json = r#"{
            "id": "chunk_123",
            "x": 0.5,
            "y": 0.75
        }"#;

        let point: EmbeddingPoint = serde_json::from_str(json).unwrap();

        assert_eq!(point.id, "chunk_123");
        assert_eq!(point.path, "");
        assert_eq!(point.chunk_type, "");
    }

    #[test]
    fn test_rag_embeddings_response_deserialize() {
        let json = r#"{
            "points": [
                {"id": "chunk1", "x": 0.1, "y": 0.2, "path": "a.rs", "type": "function"},
                {"id": "chunk2", "x": 0.3, "y": 0.4, "path": "b.rs", "type": "class"}
            ],
            "count": 2
        }"#;

        let response: RagEmbeddingsResponse = serde_json::from_str(json).unwrap();

        assert_eq!(response.count, 2);
        assert_eq!(response.points.len(), 2);
        assert_eq!(response.points[0].id, "chunk1");
        assert_eq!(response.points[1].id, "chunk2");
        assert!(response.error.is_none());
    }

    #[test]
    fn test_rag_embeddings_response_with_error() {
        let json = r#"{
            "points": [],
            "count": 0,
            "error": "RAG not initialized"
        }"#;

        let response: RagEmbeddingsResponse = serde_json::from_str(json).unwrap();

        assert_eq!(response.count, 0);
        assert!(response.points.is_empty());
        assert_eq!(response.error, Some("RAG not initialized".to_string()));
    }

    #[test]
    fn test_stream_notification_chunk_parsing() {
        let json = r#"{"chunk": "Hello world"}"#;
        let params: serde_json::Value = serde_json::from_str(json).unwrap();

        let chunk = params.get("chunk").and_then(|v| v.as_str());
        assert_eq!(chunk, Some("Hello world"));
    }

    #[test]
    fn test_stream_notification_done_with_tokens() {
        let json = r#"{
            "done": true,
            "tokens": {
                "total_input": 50,
                "total_output": 100,
                "total_tokens": 150,
                "total_cost": 0.002,
                "request_count": 1
            }
        }"#;

        let params: serde_json::Value = serde_json::from_str(json).unwrap();

        let done = params.get("done").and_then(|v| v.as_bool()).unwrap_or(false);
        assert!(done);

        let tokens = params
            .get("tokens")
            .and_then(|v| serde_json::from_value::<TokenStats>(v.clone()).ok());

        assert!(tokens.is_some());
        let stats = tokens.unwrap();
        assert_eq!(stats.total_tokens, 150);
        assert_eq!(stats.total_input, 50);
        assert_eq!(stats.total_output, 100);
    }

    #[test]
    fn test_stream_notification_done_without_tokens() {
        let json = r#"{"done": true}"#;
        let params: serde_json::Value = serde_json::from_str(json).unwrap();

        let done = params.get("done").and_then(|v| v.as_bool()).unwrap_or(false);
        assert!(done);

        let tokens = params
            .get("tokens")
            .and_then(|v| serde_json::from_value::<TokenStats>(v.clone()).ok());

        assert!(tokens.is_none());
    }

    #[test]
    fn test_rag_status_response_deserialize() {
        let json = r#"{
            "initialized": true,
            "count": 42,
            "db_path": "/path/to/db",
            "collection": "my_collection"
        }"#;

        let response: RagStatusResponse = serde_json::from_str(json).unwrap();

        assert!(response.initialized);
        assert_eq!(response.count, 42);
    }

    #[test]
    fn test_rag_status_response_not_initialized() {
        let json = r#"{
            "initialized": false,
            "count": 0
        }"#;

        let response: RagStatusResponse = serde_json::from_str(json).unwrap();

        assert!(!response.initialized);
        assert_eq!(response.count, 0);
    }
}
