begin;

-- =========================================================
-- 1. Extensions
-- =========================================================

create extension if not exists vector;
create extension if not exists pgcrypto;


-- =========================================================
-- 2. Internal RAG schema
-- =========================================================

create schema if not exists rag;


-- =========================================================
-- 3. Move the old vector table into rag.chunks
-- =========================================================

do $$
begin
    -- Existing table is still public.rag_chunks.
    if to_regclass('public.rag_chunks') is not null
       and to_regclass('rag.chunks') is null then

        alter table public.rag_chunks set schema rag;
        alter table rag.rag_chunks rename to chunks;

    -- Table was moved to rag but not renamed yet.
    elsif to_regclass('rag.rag_chunks') is not null
       and to_regclass('rag.chunks') is null then

        alter table rag.rag_chunks rename to chunks;
    end if;
end
$$;


-- Create the vector table from scratch when no previous table exists.
create table if not exists rag.chunks (
    id bigserial primary key,

    chunk_id text unique not null,
    document_id text not null,
    chunk_type text,

    content text not null,

    document_title text,
    document_number text,
    document_type text,
    issuing_authority text,

    issue_date date,
    effective_date date,
    expiry_date date,
    status text,

    source_url text,
    local_path text,

    article text,
    article_number text,
    article_title text,
    chapter text,
    section text,

    paragraph_start integer,
    paragraph_end integer,

    metadata jsonb not null default '{}'::jsonb,

    embedding public.vector(768),

    created_at timestamptz not null default now()
);


-- =========================================================
-- 4. Vector database indexes
-- =========================================================

create index if not exists rag_chunks_document_id_idx
on rag.chunks(document_id);

create index if not exists rag_chunks_document_number_idx
on rag.chunks(document_number);

create index if not exists rag_chunks_effective_date_idx
on rag.chunks(effective_date);

create index if not exists rag_chunks_metadata_gin_idx
on rag.chunks
using gin(metadata);

create index if not exists rag_chunks_embedding_hnsw_idx
on rag.chunks
using hnsw (embedding public.vector_cosine_ops);


-- =========================================================
-- 5. Keep the rag schema private from Supabase frontend roles
-- =========================================================

-- Backend connects through PostgreSQL credentials.
-- Frontend anon/authenticated roles must not access rag directly.
alter table rag.chunks disable row level security;

revoke all on schema rag from anon, authenticated;
revoke all on all tables in schema rag from anon, authenticated;
revoke all on all sequences in schema rag from anon, authenticated;
revoke all on all functions in schema rag from anon, authenticated;

alter default privileges in schema rag
revoke all on tables from anon, authenticated;

alter default privileges in schema rag
revoke all on sequences from anon, authenticated;

alter default privileges in schema rag
revoke all on functions from anon, authenticated;


-- =========================================================
-- 6. Remove old public vector search functions
-- =========================================================

drop function if exists public.match_rag_chunks(
    public.vector,
    integer
);

drop function if exists public.match_rag_chunks(
    public.vector,
    integer,
    double precision
);

drop function if exists public.match_rag_chunks(
    public.vector,
    integer,
    jsonb
);


-- =========================================================
-- 7. Private vector search function in rag schema
-- =========================================================

drop function if exists rag.match_chunks(
    public.vector,
    integer,
    double precision,
    date
);

create function rag.match_chunks(
    query_embedding public.vector(768),
    match_count integer default 5,
    min_similarity double precision default 0.0,
    query_date date default current_date
)
returns table (
    chunk_id text,
    document_id text,
    chunk_type text,
    content text,

    document_title text,
    document_number text,
    document_type text,

    article text,
    article_number text,
    article_title text,

    source_url text,
    metadata jsonb,
    similarity double precision
)
language sql
stable
set search_path = rag, public
as $$
    select
        c.chunk_id,
        c.document_id,
        c.chunk_type,
        c.content,

        c.document_title,
        c.document_number,
        c.document_type,

        c.article,
        c.article_number,
        c.article_title,

        c.source_url,
        c.metadata,

        (
            1 - (
                c.embedding
                OPERATOR(public.<=>)
                query_embedding
            )
        )::double precision as similarity

    from rag.chunks as c

    where c.embedding is not null

      and (
          1 - (
              c.embedding
              OPERATOR(public.<=>)
              query_embedding
          )
      ) >= min_similarity

      and (
          c.effective_date is null
          or c.effective_date <= query_date
      )

      and (
          c.expiry_date is null
          or c.expiry_date >= query_date
      )

    order by
        c.embedding
        OPERATOR(public.<=>)
        query_embedding

    limit match_count;
$$;

revoke all on function rag.match_chunks(
    public.vector,
    integer,
    double precision,
    date
) from public, anon, authenticated;


-- =========================================================
-- 8. User profiles
-- =========================================================

create table if not exists public.profiles (
    id uuid primary key
        references auth.users(id)
        on delete cascade,

    display_name text,
    avatar_url text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


-- =========================================================
-- 9. Conversations
-- =========================================================

create table if not exists public.conversations (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    title text not null default 'Cuoc tro chuyen moi',

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists conversations_user_id_idx
on public.conversations(user_id);

create index if not exists conversations_updated_at_idx
on public.conversations(updated_at desc);


-- =========================================================
-- 10. Messages
-- =========================================================

create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),

    conversation_id uuid not null
        references public.conversations(id)
        on delete cascade,

    user_id uuid
        references auth.users(id)
        on delete set null,

    role text not null
        check (role in ('user', 'assistant', 'system')),

    content text not null,

    citations jsonb not null default '[]'::jsonb,
    retrieval_metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now()
);

create index if not exists messages_conversation_id_idx
on public.messages(conversation_id);

create index if not exists messages_conversation_created_idx
on public.messages(conversation_id, created_at);


-- =========================================================
-- 11. Feedback
-- =========================================================

create table if not exists public.feedback (
    id uuid primary key default gen_random_uuid(),

    message_id uuid not null
        references public.messages(id)
        on delete cascade,

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    rating smallint
        check (rating in (-1, 1)),

    comment text,

    created_at timestamptz not null default now(),

    unique (message_id, user_id)
);

create index if not exists feedback_user_id_idx
on public.feedback(user_id);


-- =========================================================
-- 12. Enable RLS for frontend tables
-- =========================================================

alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.feedback enable row level security;


-- =========================================================
-- 13. Drop old policies
-- =========================================================

drop policy if exists "Users can read own profile"
on public.profiles;

drop policy if exists "Users can insert own profile"
on public.profiles;

drop policy if exists "Users can update own profile"
on public.profiles;

drop policy if exists "Users can read own conversations"
on public.conversations;

drop policy if exists "Users can create own conversations"
on public.conversations;

drop policy if exists "Users can update own conversations"
on public.conversations;

drop policy if exists "Users can delete own conversations"
on public.conversations;

drop policy if exists "Users can read messages in own conversations"
on public.messages;

drop policy if exists "Users can insert own user messages"
on public.messages;

drop policy if exists "Users can read own feedback"
on public.feedback;

drop policy if exists "Users can create own feedback"
on public.feedback;

drop policy if exists "Users can update own feedback"
on public.feedback;

drop policy if exists "Users can delete own feedback"
on public.feedback;


-- =========================================================
-- 14. Profile policies
-- =========================================================

create policy "Users can read own profile"
on public.profiles
for select
to authenticated
using (
    id = (select auth.uid())
);

create policy "Users can insert own profile"
on public.profiles
for insert
to authenticated
with check (
    id = (select auth.uid())
);

create policy "Users can update own profile"
on public.profiles
for update
to authenticated
using (
    id = (select auth.uid())
)
with check (
    id = (select auth.uid())
);


-- =========================================================
-- 15. Conversation policies
-- =========================================================

create policy "Users can read own conversations"
on public.conversations
for select
to authenticated
using (
    user_id = (select auth.uid())
);

create policy "Users can create own conversations"
on public.conversations
for insert
to authenticated
with check (
    user_id = (select auth.uid())
);

create policy "Users can update own conversations"
on public.conversations
for update
to authenticated
using (
    user_id = (select auth.uid())
)
with check (
    user_id = (select auth.uid())
);

create policy "Users can delete own conversations"
on public.conversations
for delete
to authenticated
using (
    user_id = (select auth.uid())
);


-- =========================================================
-- 16. Message policies
-- =========================================================

create policy "Users can read messages in own conversations"
on public.messages
for select
to authenticated
using (
    exists (
        select 1
        from public.conversations as c
        where c.id = messages.conversation_id
          and c.user_id = (select auth.uid())
    )
);

-- Frontend can insert user messages only.
-- Assistant/system messages should be stored by the FastAPI backend.
create policy "Users can insert own user messages"
on public.messages
for insert
to authenticated
with check (
    user_id = (select auth.uid())
    and role = 'user'
    and exists (
        select 1
        from public.conversations as c
        where c.id = messages.conversation_id
          and c.user_id = (select auth.uid())
    )
);


-- =========================================================
-- 17. Feedback policies
-- =========================================================

create policy "Users can read own feedback"
on public.feedback
for select
to authenticated
using (
    user_id = (select auth.uid())
);

create policy "Users can create own feedback"
on public.feedback
for insert
to authenticated
with check (
    user_id = (select auth.uid())
    and exists (
        select 1
        from public.messages as m
        join public.conversations as c
          on c.id = m.conversation_id
        where m.id = feedback.message_id
          and c.user_id = (select auth.uid())
    )
);

create policy "Users can update own feedback"
on public.feedback
for update
to authenticated
using (
    user_id = (select auth.uid())
)
with check (
    user_id = (select auth.uid())
);

create policy "Users can delete own feedback"
on public.feedback
for delete
to authenticated
using (
    user_id = (select auth.uid())
);


-- =========================================================
-- 18. updated_at trigger
-- =========================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists profiles_set_updated_at
on public.profiles;

create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();

drop trigger if exists conversations_set_updated_at
on public.conversations;

create trigger conversations_set_updated_at
before update on public.conversations
for each row
execute function public.set_updated_at();


commit;
