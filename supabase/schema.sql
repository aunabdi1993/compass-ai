-- Compass Phase 1 schema. Run once in the Supabase SQL editor.
-- Row Level Security means each signed-in user can only touch their own rows,
-- even though the app uses the public anon key.

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

create policy "own profile" on public.profiles
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

create policy "own conversations" on public.conversations
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Messages may only be written into a conversation the user owns.
create policy "own messages" on public.messages
  for all using (user_id = auth.uid())
  with check (
    user_id = auth.uid()
    and exists (
      select 1 from public.conversations c
      where c.id = conversation_id and c.user_id = auth.uid()
    )
  );
