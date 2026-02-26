import supabase
from supabase import create_client, Client
from core.config import settings
from typing import List, Dict, Any

url: str = settings.supabase_url
key: str = settings.supabase_key
supabase_client: Client = create_client(url, key)

def insert_policy_chunks(chunks_data: List[Dict[str, Any]]):
    """Inserts a list of dictionary chunks into Supabase."""
    return supabase_client.table("policy_chunks").insert(chunks_data).execute()

def match_policy_chunks(embedding: List[float], match_count: int = 5, match_threshold: float = 0.6):
    """Searches Supabase for similar chunks using pgvector match function."""
    response = supabase_client.rpc(
        "match_policy_chunks",
        {
            "query_embedding": embedding,
            "match_threshold": match_threshold,
            "match_count": match_count
        }
    ).execute()
    return response.data

def insert_audit_result(question_text: str, status: str, evidence: str):
    """Inserts an evaluated audit result into Supabase."""
    data = {
        "question_text": question_text,
        "status": status,
        "evidence": evidence
    }
    return supabase_client.table("audit_results").insert(data).execute()

def get_all_audit_results():
    """Retrieves all audit results from Supabase."""
    return supabase_client.table("audit_results").select("*").execute()

def clear_data():
    """Deletes all data from the database to reset the application state."""
    # To delete all rows safely without requiring a matching ID, we can use an unconstrained delete,
    # or delete where id is not null.
    supabase_client.table("audit_results").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    supabase_client.table("policy_chunks").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    return {"message": "Database cleared."}
