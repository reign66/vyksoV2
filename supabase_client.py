import os
from supabase import create_client, Client
from typing import Optional

def get_supabase_client() -> Client:
    """
    Retourne un client Supabase configuré
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        raise ValueError("Missing Supabase credentials in environment variables")
    
    return create_client(url, key)

# Singleton instance
_supabase_client: Optional[Client] = None

def get_client() -> Client:
    """Get or create Supabase client singleton"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase_client()
    return _supabase_client
