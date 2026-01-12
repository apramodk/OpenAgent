import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection("codebase_specs")

results = collection.query(
    query_texts=["how does the agent work?"],
    n_results=3
)

for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f"[{meta.get('type', 'unknown')}] {doc}\n")