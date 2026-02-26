-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create policy_chunks table
create table policy_chunks (
  id uuid primary key default gen_random_uuid(),
  policy_name text not null,
  chunk_text text not null,
  embedding vector(3072)
);

-- We cannot use HNSW index because pgvector restricts HNSW to a maximum of 2,000 dimensions.
-- gemini-embedding-001 vectors are 3,072 dimensions. 
-- For small to medium datasets, Exact Nearest Neighbor (KNN) table scans are acceptable.
-- For massive scale, you would need IVFFlat indexing or an embedding model with fewer dimensions.

-- Create audit_results table
create table audit_results (
  id uuid primary key default gen_random_uuid(),
  question_text text not null,
  status text not null,
  evidence text not null
);

-- Create a function to search for policy chunks
create or replace function match_policy_chunks (
  query_embedding vector(3072),
  match_threshold float,
  match_count int
)
returns table (
  id uuid,
  policy_name text,
  chunk_text text,
  similarity float
)
language sql stable
as $$
  select
    policy_chunks.id,
    policy_chunks.policy_name,
    policy_chunks.chunk_text,
    1 - (policy_chunks.embedding <=> query_embedding) as similarity
  from policy_chunks
  where 1 - (policy_chunks.embedding <=> query_embedding) > match_threshold
  order by policy_chunks.embedding <=> query_embedding
  limit match_count;
$$;
