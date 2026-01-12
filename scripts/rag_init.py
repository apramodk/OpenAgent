import chromadb
import sys
import json

def load_specs(json_path):
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection("codebase_specs")

    with open(json_path) as f:
        spec = json.load(f)

    # Add file chunks
    for chunk in spec.get("file_chunks", []):
        metadata = chunk["metadata"].copy()
        # Convert list to comma-separated string
        if "concepts" in metadata:
            metadata["concepts"] = ", ".join(metadata["concepts"])
        
        collection.add(
            ids=[chunk["id"]],
            documents=[chunk["content"]],
            metadatas=[metadata]
        )
        print(f"Added file: {chunk['id']}")

    # Add code unit chunks
    for chunk in spec.get("code_unit_chunks", []):
        metadata = chunk["metadata"].copy()
        # Convert lists to comma-separated strings
        if "calls" in metadata:
            metadata["calls"] = ", ".join(metadata["calls"])
        if "called_by" in metadata:
            metadata["called_by"] = ", ".join(metadata["called_by"])
        
        collection.add(
            ids=[chunk["id"]],
            documents=[chunk["content"]],
            metadatas=[metadata]
        )
        print(f"Added code unit: {chunk['id']}")

    print(f"\nTotal documents: {collection.count()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 rag.py <json_file>")
        sys.exit(1)
    
    load_specs(sys.argv[1])