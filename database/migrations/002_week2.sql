-- Week 2: consent, thumbs feedback, uploaded documents, delete-my-data.
-- Run once in the Supabase SQL editor if you already ran the Week 1 schema.
-- (database/schema.sql contains the same objects for fresh projects.)

-- 1. Consent -------------------------------------------------------------
create table if not exists public.consents (
  user_id         uuid primary key references auth.users (id) on delete cascade default auth.uid(),
  version         text not null,
  accepted_at     timestamptz not null default now(),
  training_opt_in boolean not null default false,  -- separate, optional opt-in
  updated_at      timestamptz not null default now()
);
alter table public.consents enable row level security;
drop policy if exists "own consent" on public.consents;
create policy "own consent" on public.consents
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- 2. Thumbs up/down saved with the coach's reply ---------------------------
alter table public.messages add column if not exists feedback smallint
  check (feedback in (-1, 1));
alter table public.messages add column if not exists feedback_at timestamptz;

-- 3. Uploaded documents used as coaching context ---------------------------
create table if not exists public.documents (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade default auth.uid(),
  name       text not null,
  content    text not null,              -- extracted text, not the original file
  char_count integer not null,
  truncated  boolean not null default false,
  enabled    boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists documents_user_created_idx
  on public.documents (user_id, created_at desc);
alter table public.documents enable row level security;
drop policy if exists "own documents" on public.documents;
create policy "own documents" on public.documents
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- 4. Delete my data: one atomic call; Row Level Security still applies --------
-- Removes chats (and their messages), documents, profile and consent record.
-- The sign-in account itself stays; delete it from Supabase > Authentication.
create or replace function public.delete_my_data()
returns void
language plpgsql
security invoker
as $$
begin
  delete from public.conversations where user_id = auth.uid();  -- cascades to messages
  delete from public.documents     where user_id = auth.uid();
  delete from public.profiles      where user_id = auth.uid();
  delete from public.consents      where user_id = auth.uid();
end;
$$;
revoke all on function public.delete_my_data() from public, anon;
grant execute on function public.delete_my_data() to authenticated;
