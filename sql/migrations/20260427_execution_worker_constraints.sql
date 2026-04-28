-- Add integrity constraints for status and retry counters.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'build_packets_status_check'
  ) THEN
    ALTER TABLE build_packets
      ADD CONSTRAINT build_packets_status_check
      CHECK (status in ('queued', 'running', 'completed', 'failed')) NOT VALID;
    ALTER TABLE build_packets
      VALIDATE CONSTRAINT build_packets_status_check;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'build_packets_attempts_nonnegative_check'
  ) THEN
    ALTER TABLE build_packets
      ADD CONSTRAINT build_packets_attempts_nonnegative_check
      CHECK (attempts >= 0) NOT VALID;
    ALTER TABLE build_packets
      VALIDATE CONSTRAINT build_packets_attempts_nonnegative_check;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'build_packets_max_attempts_min_one_check'
  ) THEN
    ALTER TABLE build_packets
      ADD CONSTRAINT build_packets_max_attempts_min_one_check
      CHECK (max_attempts >= 1) NOT VALID;
    ALTER TABLE build_packets
      VALIDATE CONSTRAINT build_packets_max_attempts_min_one_check;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'execution_runs_status_check'
  ) THEN
    ALTER TABLE execution_runs
      ADD CONSTRAINT execution_runs_status_check
      CHECK (status in ('running', 'completed', 'failed')) NOT VALID;
    ALTER TABLE execution_runs
      VALIDATE CONSTRAINT execution_runs_status_check;
  END IF;
END
$$;
