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

create index if not exists rag_chunks_full_text_idx
on rag.chunks
using gin (
    (
        setweight(to_tsvector('simple', coalesce(document_title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(document_number, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(article, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(article_title, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'C')
    )
);


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
-- 5A. Internal monitoring tables
-- =========================================================

create table if not exists rag.query_logs (
    id uuid primary key default gen_random_uuid(),

    created_at timestamptz not null default now(),

    conversation_id text,
    user_id text,
    assistant_message_id text,

    status text not null default 'success'
        check (
            status in (
                'success',
                'blocked',
                'rejected',
                'clarification_required',
                'llm_fallback',
                'error'
            )
        ),
    mode text,

    original_question text,
    normalized_question text,
    standalone_question text,
    retrieval_query text,

    intent text,
    route text,
    confidence double precision,

    top_k integer,
    retrieved_count integer,
    reranked_count integer,
    prompt_estimated_tokens integer,

    llm_provider text,
    llm_model text,
    llm_prompt_estimated_tokens integer,
    llm_max_output_tokens integer,
    llm_prompt_tokens integer,
    llm_completion_tokens integer,
    llm_total_tokens integer,
    llm_estimated_cost_usd double precision,

    response_time_ms integer,
    answer text,
    warnings jsonb not null default '[]'::jsonb,

    error_type text,
    error_message text,

    request_payload jsonb,
    processed_question jsonb,
    classification jsonb,
    routing jsonb,
    query_embedding jsonb,
    retrieval jsonb,
    reranking jsonb,
    tax_calculation jsonb,
    context_metadata jsonb,
    prompt_metadata jsonb,
    llm jsonb,
    response_validation jsonb,
    citations jsonb not null default '[]'::jsonb
);

create index if not exists query_logs_created_at_idx
on rag.query_logs(created_at desc);

create index if not exists query_logs_status_idx
on rag.query_logs(status);

create index if not exists query_logs_user_id_idx
on rag.query_logs(user_id);

create index if not exists query_logs_conversation_id_idx
on rag.query_logs(conversation_id);

create index if not exists query_logs_confidence_idx
on rag.query_logs(confidence);


create table if not exists rag.query_log_chunks (
    id bigserial primary key,

    query_log_id uuid not null
        references rag.query_logs(id)
        on delete cascade,

    created_at timestamptz not null default now(),

    citation_id text,
    chunk_id text,
    document_id text,
    document_number text,
    document_name text,
    document_type text,
    article text,
    source_url text,

    retrieval_rank integer,
    rerank_rank integer,
    similarity double precision,
    rerank_score double precision,

    content_preview text,
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists query_log_chunks_query_log_id_idx
on rag.query_log_chunks(query_log_id);

create index if not exists query_log_chunks_chunk_id_idx
on rag.query_log_chunks(chunk_id);

create index if not exists query_log_chunks_document_number_idx
on rag.query_log_chunks(document_number);

create index if not exists query_log_chunks_created_at_idx
on rag.query_log_chunks(created_at desc);


create table if not exists rag.ingestion_runs (
    id uuid primary key default gen_random_uuid(),

    created_at timestamptz not null default now(),
    finished_at timestamptz,

    run_name text not null,
    status text not null default 'running'
        check (status in ('running', 'success', 'warning', 'error')),

    total_documents integer not null default 0,
    success_count integer not null default 0,
    warning_count integer not null default 0,
    error_count integer not null default 0,

    note text
);

create index if not exists ingestion_runs_created_at_idx
on rag.ingestion_runs(created_at desc);

create index if not exists ingestion_runs_status_idx
on rag.ingestion_runs(status);


create table if not exists rag.ingestion_document_logs (
    id bigserial primary key,

    created_at timestamptz not null default now(),
    run_id uuid
        references rag.ingestion_runs(id)
        on delete cascade,

    document_id text,
    step text not null,
    status text not null
        check (status in ('success', 'warning', 'empty', 'error', 'skipped')),

    input_path text,
    output_path text,

    char_count integer,
    chunk_count integer,
    page_count integer,

    warning text,
    error_message text,
    raw_log jsonb not null default '{}'::jsonb
);

create index if not exists ingestion_document_logs_created_at_idx
on rag.ingestion_document_logs(created_at desc);

create index if not exists ingestion_document_logs_run_id_idx
on rag.ingestion_document_logs(run_id);

create index if not exists ingestion_document_logs_document_id_idx
on rag.ingestion_document_logs(document_id);

create index if not exists ingestion_document_logs_status_idx
on rag.ingestion_document_logs(status);

create index if not exists ingestion_document_logs_step_idx
on rag.ingestion_document_logs(step);


create table if not exists rag.documents (
    document_id text primary key,

    file_name text,
    document_title text,
    document_number text,
    document_type text,
    issuing_authority text,

    issue_date date,
    effective_date date,
    expiry_date date,
    status text not null default 'draft'
        check (
            status in (
                'draft',
                'effective',
                'partially_effective',
                'expired',
                'superseded'
            )
        ),

    source_url text,
    local_path text,
    version text,
    topics text,
    notes text,

    extractor text,
    page_count integer,
    extracted_char_count integer not null default 0,
    extracted_preview text,

    ingestion_status text not null default 'uploaded'
        check (
            ingestion_status in (
                'uploaded',
                'extracted',
                'ingesting',
                'indexed',
                'error',
                'removed_from_search'
            )
        ),
    ingestion_error text,

    search_enabled boolean not null default false,
    chunk_count integer not null default 0,
    last_ingested_at timestamptz,

    metadata jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists documents_document_number_idx
on rag.documents(document_number);

create index if not exists documents_status_idx
on rag.documents(status);

create index if not exists documents_ingestion_status_idx
on rag.documents(ingestion_status);

create index if not exists documents_search_enabled_idx
on rag.documents(search_enabled);

create index if not exists documents_updated_at_idx
on rag.documents(updated_at desc);

create index if not exists documents_metadata_gin_idx
on rag.documents
using gin(metadata);

create table if not exists rag.tax_rules (
    rule_id text primary key,
    tax_year_from integer not null,
    tax_year_to integer,
    effective_from date,
    effective_to date,
    source_documents jsonb not null default '[]'::jsonb,
    rule_payload jsonb not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists tax_rules_tax_year_idx
on rag.tax_rules(tax_year_from, tax_year_to);

create index if not exists tax_rules_active_idx
on rag.tax_rules(is_active);

insert into rag.tax_rules (
    rule_id,
    tax_year_from,
    tax_year_to,
    effective_from,
    effective_to,
    source_documents,
    rule_payload
)
values
(
    'pit_salary_resident_progressive_2020_2025',
    2020,
    2025,
    date '2020-01-01',
    date '2025-12-31',
    '["RESOLUTION_954_2020_UBTVQH14","CIRCULAR_111_2013_TT_BTC"]'::jsonb,
    '{
      "rule_id": "pit_salary_resident_progressive_2020_2025",
      "description": "Resident personal income tax for salary/wage income, monthly calculation, family deduction under Resolution 954/2020/UBTVQH14 and progressive brackets from Circular 111/2013/TT-BTC.",
      "source_documents": ["RESOLUTION_954_2020_UBTVQH14", "CIRCULAR_111_2013_TT_BTC"],
      "tax_year_from": 2020,
      "tax_year_to": 2025,
      "effective_from": "2020-01-01",
      "effective_to": "2025-12-31",
      "personal_deduction_monthly": 11000000,
      "dependent_deduction_monthly": 4400000,
      "resident_brackets_monthly": [
        {"up_to": 5000000, "rate": 0.05},
        {"up_to": 10000000, "rate": 0.1},
        {"up_to": 18000000, "rate": 0.15},
        {"up_to": 32000000, "rate": 0.2},
        {"up_to": 52000000, "rate": 0.25},
        {"up_to": 80000000, "rate": 0.3},
        {"up_to": null, "rate": 0.35}
      ],
      "non_resident_salary_rate": 0.2,
      "short_term_withholding_rate": 0.1
    }'::jsonb
),
(
    'pit_salary_resident_progressive_2026',
    2026,
    null,
    date '2026-01-01',
    null,
    '["LAW_109_2025_QH15"]'::jsonb,
    '{
      "rule_id": "pit_salary_resident_progressive_2026",
      "description": "Resident personal income tax for salary/wage income from tax year 2026 under Law 109/2025/QH15.",
      "source_documents": ["LAW_109_2025_QH15"],
      "tax_year_from": 2026,
      "tax_year_to": null,
      "effective_from": "2026-01-01",
      "effective_to": null,
      "personal_deduction_monthly": 15500000,
      "dependent_deduction_monthly": 6200000,
      "resident_brackets_monthly": [
        {"up_to": 10000000, "rate": 0.05},
        {"up_to": 30000000, "rate": 0.1},
        {"up_to": 60000000, "rate": 0.2},
        {"up_to": 100000000, "rate": 0.3},
        {"up_to": null, "rate": 0.35}
      ],
      "non_resident_salary_rate": 0.2,
      "short_term_withholding_rate": 0.1
    }'::jsonb
)
on conflict (rule_id) do update set
    tax_year_from = excluded.tax_year_from,
    tax_year_to = excluded.tax_year_to,
    effective_from = excluded.effective_from,
    effective_to = excluded.effective_to,
    source_documents = excluded.source_documents,
    rule_payload = excluded.rule_payload,
    updated_at = now();

alter table rag.query_logs disable row level security;
alter table rag.query_log_chunks disable row level security;
alter table rag.ingestion_runs disable row level security;
alter table rag.ingestion_document_logs disable row level security;
alter table rag.documents disable row level security;
alter table rag.tax_rules disable row level security;

revoke all on table
    rag.query_logs,
    rag.query_log_chunks,
    rag.ingestion_runs,
    rag.ingestion_document_logs,
    rag.documents,
    rag.tax_rules
from anon, authenticated;

revoke all on all sequences in schema rag from anon, authenticated;


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

    title text not null default 'Cuộc trò chuyện mới',

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

drop trigger if exists documents_set_updated_at
on rag.documents;

create trigger documents_set_updated_at
before update on rag.documents
for each row
execute function public.set_updated_at();

drop trigger if exists tax_rules_set_updated_at
on rag.tax_rules;

create trigger tax_rules_set_updated_at
before update on rag.tax_rules
for each row
execute function public.set_updated_at();


commit;