-- First, drop the dependent function and index
drop function if exists match_policy_chunks;
drop index if exists policy_chunks_embedding_idx;

-- Alter the table to accept the new dimension size
alter table policy_chunks alter column embedding type vector(3072);

-- We omit the HNSW index here because pgvector limits HNSW to <= 2000 dimensions

-- Recreate the function with the correct dimension size
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
