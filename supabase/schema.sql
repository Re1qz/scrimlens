-- SCRIMLENS Supabase Schema

create extension if not exists "uuid-ossp";

-- スクリムセッション
create table scrims (
  id uuid primary key default uuid_generate_v4(),
  url text not null,
  title text,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'error')),
  error_message text,
  retry_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- チーム（スクリムごと）
create table teams (
  id uuid primary key default uuid_generate_v4(),
  scrim_id uuid not null references scrims(id) on delete cascade,
  name text not null,
  team_num integer,
  total_kills integer not null default 0,
  total_placement integer not null default 0,
  total_damage integer not null default 0,
  total_points integer not null default 0,
  rank integer,
  created_at timestamptz not null default now()
);

-- ゲーム（試合）
create table games (
  id uuid primary key default uuid_generate_v4(),
  scrim_id uuid not null references scrims(id) on delete cascade,
  game_num integer not null,
  created_at timestamptz not null default now()
);

-- プレイヤー統計（1試合ごと）
create table player_stats (
  id uuid primary key default uuid_generate_v4(),
  scrim_id uuid not null references scrims(id) on delete cascade,
  game_id uuid references games(id) on delete cascade,
  team_id uuid references teams(id) on delete cascade,
  player_name text not null,
  character text,
  placement integer,
  kills integer not null default 0,
  assists integer not null default 0,
  damage integer not null default 0,
  survival_time text,
  created_at timestamptz not null default now()
);

-- updated_at自動更新
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger scrims_updated_at
  before update on scrims
  for each row execute function update_updated_at();

-- インデックス
create index idx_scrims_status on scrims(status);
create index idx_teams_scrim_id on teams(scrim_id);
create index idx_games_scrim_id on games(scrim_id);
create index idx_player_stats_scrim_id on player_stats(scrim_id);
create index idx_player_stats_team_id on player_stats(team_id);

-- Row Level Security（公開読み取り、書き込みはservice_role）
alter table scrims enable row level security;
alter table teams enable row level security;
alter table games enable row level security;
alter table player_stats enable row level security;

create policy "public read scrims" on scrims for select using (true);
create policy "public read teams" on teams for select using (true);
create policy "public read games" on games for select using (true);
create policy "public read player_stats" on player_stats for select using (true);
