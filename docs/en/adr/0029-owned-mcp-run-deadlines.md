# ADR-0029: Own the process tree of an MCP run

Status: implemented (engineering, Windows verified).

## Context

The MCP deadline killed only the immediate CLI. Pytest and browser descendants
could outlive it, and the error discarded the partial run reference. Inherited
output pipes can also make cleanup wait for surviving descendants.

## Options compared

- Kill the root only: insufficient ownership.
- Enumerate descendants at timeout: racy if an intermediate parent exits.
- Windows process job / POSIX process group: explicit lifetime boundary.

## Decision

Use a non-inheritable Windows job with kill-on-close, assigned to an isolated
Python gate before project code can launch. Assignment failure closes the gate
without running the project. POSIX launches a new session and closes its process
group. Cleanup runs on timeout, interruption and normal root exit. Temporary
file-backed output avoids inherited pipe waits and bounds diagnostic memory.

Timeout is a structured MCP tool error: null exit code, deadline marker, partial
run directory, truthful inspect summary and sanitized output tails. Do not append
a synthetic `run.end` or claim assurance for an interrupted test.

## Consequences

No new dependencies. Background children started by these tests do not persist
after a tool run. Deliberately detached POSIX processes are outside the group;
this is a lifecycle boundary for trusted code, not a security sandbox. Temporary
output uses disk during the command. Non-Windows branches still require the
support matrix; a Windows receipt does not verify them.

## Tripwire

Synthetic child/grandchild listeners must stop at a deadline and after normal
parent exit while an unrelated process remains alive. A real pytest deadline
must retain its incomplete ledger and leave the MCP server usable.

API contracts: [Microsoft process jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [assignment rights](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject).
