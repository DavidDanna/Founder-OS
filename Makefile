.PHONY: queue-approved-tasks worker-once worker-loop test-worker

queue-approved-tasks:
	python worker/packet_coordinator.py

worker-once:
	RUN_ONCE=true python worker/execution_worker.py

worker-loop:
	python worker/execution_worker.py

test-worker:
	python -m unittest worker/test_execution_worker.py worker/test_packet_coordinator.py
