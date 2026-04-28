-- Add retry metadata for build packet processing

alter table if exists build_packets
  add column if not exists attempts int not null default 0;

alter table if exists build_packets
  add column if not exists max_attempts int not null default 3;
