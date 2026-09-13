# Workspace visual contract

Local synthetic UI only. At each declared viewport, overview and invitation dialog
must retain the accepted appearance. The invitation button remains operable.
No backend, authentication or persistence claim. A DOM-only refactor must remain
green. Shifted content, invisible values and clipped mobile layout must be detected.
Missing/tampered baseline and incompatible profile must abstain, not prove a bug.
Baseline creation is a separate authoring phase. Replay never updates baselines.

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "client-simulation",
  "id": "workspace.visual",
  "title": "Synthetic workspace visual regression",
  "claims": [{"id": "workspace.visual", "statement": "The ready workspace viewport matches the accepted visual contract", "oracles": ["ui"], "required": true}],
  "assertions": [
    {"id": "a.ready", "claim_id": "workspace.visual", "oracle": "ui", "required": true, "expected": "State heading visible after user action"},
    {"id": "a.visual", "claim_id": "workspace.visual", "oracle": "ui", "required": true, "expected": "Pixels match the digest-pinned viewport baseline"}
  ],
  "scenarios": [{"id": "workspace-view", "title": "Inspect overview and invitation dialog", "claims": ["workspace.visual"], "risk": "Functional controls conceal broken visual layout"}]
}
```
