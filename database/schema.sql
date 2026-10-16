-- Compass Phase 1 schema (Weeks 1 and 2). Safe to re-run in the Supabase SQL editor.
-- Row Level Security means each signed-in user can only touch their own rows,
-- even though the app uses the public (publishable) key.

create table if not exists public.profiles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  role       text not null default '',
  industry   text not null default '',
  goals      text not null default '',
  cv_text    text not null default '',
  updated_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade default auth.uid(),
  summary    text,                       -- 5-line memory note, set when the session ends
  created_at timestamptz not null default now()
);
create index if not exists conversations_user_created_idx
  on public.conversations (user_id, created_at desc);

create table if not exists public.messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  user_id         uuid not null references auth.users (id) on delete cascade default auth.uid(),
  role            text not null check (role in ('user', 'assistant')),
  content         text not null,
  created_at      timestamptz not null default now()
);
create index if not exists messages_conversation_idx
  on public.messages (conversation_id, id);
create index if not exists messages_user_created_idx
  on public.messages (user_id, created_at desc);

alter table public.profiles      enable row level security;
alter table public.conversations enable row level security;
alter table public.messages      enable row level security;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "own conversations" on public.conversations;
create policy "own conversations" on public.conversations
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Messages may only be written into a conversation the user owns.
drop policy if exists "own messages" on public.messages;
create policy "own messages" on public.messages
  for all using (user_id = auth.uid())
  with check (
    user_id = auth.uid()
    and exists (
      select 1 from public.conversations c
      where c.id = conversation_id and c.user_id = auth.uid()
    )
  );

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
