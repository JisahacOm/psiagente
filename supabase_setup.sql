-- Corre esto en Supabase > SQL Editor

create table if not exists conversations (
  chat_id    text primary key,
  messages   jsonb default '[]'::jsonb,
  updated_at timestamp default now()
);

create table if not exists appointments (
  id           uuid primary key default gen_random_uuid(),
  patient_name text not null,
  phone        text,
  date         date,
  time         time,
  modality     text check (modality in ('presencial','videollamada')),
  telegram_id  text,
  status       text default 'confirmed',
  created_at   timestamp default now()
);

create table if not exists crisis_alerts (
  id           uuid primary key default gen_random_uuid(),
  telegram_id  text,
  patient_name text,
  summary      text,
  resolved     boolean default false,
  created_at   timestamp default now()
);
