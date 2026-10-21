# Worker-isolated PID receipt in browser reuse tests

Windows/Python3.12 CI38525757594 parsed an empty PID line after nested8 cases passed.
The test fixture appended to one file from4 processes. Native no-browser probe lost
720/4000 records; different-width input reproduced51 parse errors including empty
strings/spliced numbers. Separate writer files retained4000/4000 records. Original
hosted byte schedule unavailable; equivalent transport corruption reproduced.

Plan PROD-10; base d440d30794fba7bd40d0eee077cfa2a6cfd582c5; draft PR39
https://github.com/kiselas/testence/pull/39. Only test_browser_reuse.py and this audit
change. Test SHA256 2ba94714c06bead2276701e4fd36986aedc7eb9408c2691e4403d39a8be2327e.
Runtime/frozen corpus unchanged. Per-worker JSONL rows carry worker/case/PID;
every line is parsed, exact worker/case coverage and stable distinct PID required.
Keep workers4/eight cases/four browser starts and closes/namespace and context
cleanup assertions. No filtering/masking, runtime change, extra browser retry,
lower worker count or deadline increase.

Validation:13 negative/healthy reader controls plus2 extra malformed transport
controls; original live reuse suite26 passes, exact8 rows/four workers/four PIDs,
start/close4/4 and namespace absence. Last live run r-20261014-073057-8588ac under
outputs/pid-receipt-20261014-20/tmp-live-reuse/test_parallel_reuse_has_one_br0/runs.
Runtime existing CPython3.12.14/PW1.62/pytest9.1.1, Windows/Edge/debug port0;
PYTHONFAULTHANDLER=1/PYTHONIOENCODING=utf-8. Required commands:

* `outputs/quality-venv31214/Scripts/python.exe -B -m pytest -q -n 4 --basetemp=outputs/pid-receipt-20261014-20/tmp-full`: 993 passed, 2 skipped in 624.33s (0:10:24)
* Same Python Ruff format/check `src tests bench scripts examples`, mypy `src scripts`: final pass.
* Same Python `-B -m pytest examples -q --testence-headless --basetemp=outputs/pid-receipt-20261014-20/tmp-examples`:5 passed/1 skipped.

Initial Ruff failure unused import retained in wiki. Removed only top-level unused
Path; test-function/generated-consumer AST equivalence preserved with both source
hashes, full collection's exact pre/post import byte timing unobserved. No full
rerun for unchanged test bodies. No current local failed step. Prior failed step
test_parallel_reuse_has_one_browser_per_worker_and_exact_cleanup JSONDecodeError
remains window19. Internal commands/receipts/raw synthetic artifacts in sibling
wiki runs/pid-receipt-20261014-20; no new latency/independent acceptance claim.
Next `gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup`, exact new CI;
preserve any failure before new causal fix. No merge/release or hosted-success guess.
