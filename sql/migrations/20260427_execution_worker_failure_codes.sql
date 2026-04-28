-- Add failure classification fields for packet and run observability.

alter table if exists build_packets
  add column if not exists last_error_code text;

alter table if exists execution_runs
  add column if not exists failure_code text;
