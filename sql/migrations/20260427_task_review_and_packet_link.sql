-- Add review/approval state and packet linkage for task -> packet queue flow.

alter table if exists tasks
  add column if not exists review_status text default 'pending';

alter table if exists tasks
  add column if not exists approved boolean default false;

alter table if exists tasks
  add column if not exists reviewed_at timestamptz;

alter table if exists tasks
  add column if not exists approved_at timestamptz;

alter table if exists tasks
  add column if not exists build_packet_id uuid references build_packets(id) on delete set null;

alter table if exists tasks
  add column if not exists packet_generated_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'tasks_review_status_check'
  ) THEN
    ALTER TABLE tasks
      ADD CONSTRAINT tasks_review_status_check
      CHECK (review_status in ('pending', 'approved', 'rejected')) NOT VALID;
    ALTER TABLE tasks
      VALIDATE CONSTRAINT tasks_review_status_check;
  END IF;
END
$$;

update tasks
   set review_status = 'approved'
 where approved = true
   and review_status is distinct from 'approved';
