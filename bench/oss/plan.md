# External panel UI controls

Scope: local copies of the revisions in targets.json. Synthetic data only. No
login submission, backend persistence or authentication claim. UI observation is
the oracle. These cases supplement, and do not replace, the frozen release corpus.

Each repeat uses a fresh pytest process and browser. The served response can carry
a named defect (checkbox loses selection; password reveal handler absent), or a
harmless border restyle. The upstream checkout remains unchanged. Restore healthy
responses and rerun after the defect. Do not retry failed interactions.

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "oss-panels",
  "id": "oss.panels",
  "title": "External panel UI controls",
  "claims": [
    {
      "id": "admin.checkbox",
      "statement": "Checkbox selection toggles on and off",
      "oracles": [
        "ui"
      ],
      "required": true
    },
    {
      "id": "admin.radio",
      "statement": "Radio selection excludes the previous option",
      "oracles": [
        "ui"
      ],
      "required": true
    },
    {
      "id": "tabler.password",
      "statement": "Password reveal toggles masking on and off",
      "oracles": [
        "ui"
      ],
      "required": true
    },
    {
      "id": "tabler.recovery",
      "statement": "Recovery link opens the recovery form",
      "oracles": [
        "ui"
      ],
      "required": true
    }
  ],
  "assertions": [
    {
      "id": "a.checkbox.on",
      "claim_id": "admin.checkbox",
      "oracle": "ui",
      "required": true,
      "expected": "Checkbox selected"
    },
    {
      "id": "a.checkbox.off",
      "claim_id": "admin.checkbox",
      "oracle": "ui",
      "required": true,
      "expected": "Checkbox cleared"
    },
    {
      "id": "a.radio.on",
      "claim_id": "admin.radio",
      "oracle": "ui",
      "required": true,
      "expected": "Option two selected"
    },
    {
      "id": "a.radio.off",
      "claim_id": "admin.radio",
      "oracle": "ui",
      "required": true,
      "expected": "Option one cleared"
    },
    {
      "id": "a.password.show",
      "claim_id": "tabler.password",
      "oracle": "ui",
      "required": true,
      "expected": "Password revealed"
    },
    {
      "id": "a.password.hide",
      "claim_id": "tabler.password",
      "oracle": "ui",
      "required": true,
      "expected": "Password masked"
    },
    {
      "id": "a.recovery",
      "claim_id": "tabler.recovery",
      "oracle": "ui",
      "required": true,
      "expected": "Forgot password heading visible"
    }
  ],
  "scenarios": [
    {
      "id": "admin-checkbox",
      "title": "Toggle checkbox",
      "claims": [
        "admin.checkbox"
      ],
      "risk": "Click is acknowledged without state change"
    },
    {
      "id": "admin-radio",
      "title": "Choose radio",
      "claims": [
        "admin.radio"
      ],
      "risk": "Two mutually exclusive options selected"
    },
    {
      "id": "tabler-password",
      "title": "Toggle masking",
      "claims": [
        "tabler.password"
      ],
      "risk": "Reveal handler missing"
    },
    {
      "id": "tabler-recovery",
      "title": "Recover account",
      "claims": [
        "tabler.recovery"
      ],
      "risk": "Navigation leaves user on login"
    }
  ]
}
```
