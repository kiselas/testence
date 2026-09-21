"""Public artifact schema inventory for consumers and release checks."""

from __future__ import annotations

from types import MappingProxyType

from testence.assurance import ASSURANCE_POLICY_SCHEMA
from testence.engine import CAPABILITY_SCHEMA
from testence.identity import EVIDENCE_SCHEMA

from .plan import PLAN_SCHEMA
from .repair import REPAIR_SCHEMA
from .verdict import VERDICT_SCHEMA

EVIDENCE_PACK_SCHEMA = "testence/evidence-pack/2"
PACK_MANIFEST_SCHEMA = "testence/pack-manifest/2"
RUN_MANIFEST_SCHEMA = "testence/run-manifest/2"
CI_RECEIPT_SCHEMA = "testence/ci-receipt/1"
DELIVERY_RECEIPT_SCHEMA = "testence/delivery-receipt/1"
SCAFFOLD_SCHEMA = "testence/scaffold-manifest/1"
SUBMISSION_SCHEMA = "testence/verdict-submission/1"
QUALITY_PACK_SCHEMA = "testence/quality-pack/1"
QUALITY_LOCK_SCHEMA = "testence/quality-pack-lock/1"
QUALITY_SYNC_SCHEMA = "testence/quality-sync/1"
QUALITY_SUMMARY_SCHEMA = "testence/quality-summary/1"
CORPUS_REGISTRY_SCHEMA = "testence/correctness-corpus/2"
CORPUS_FREEZE_SCHEMA = "testence/correctness-corpus-freeze/1"
AGENT_INSTALL_SCHEMA = "testence/agent-install/1"
AGENT_INSTALL_RECEIPT_SCHEMA = "testence/agent-install-receipt/1"
DEMO_RUN_SCHEMA = "testence/demo-run/1"
RELEASE_MANIFEST_SCHEMA = "testence/release-manifest/2"
ACCEPTANCE_RECEIPT_SCHEMA = "testence/acceptance-receipt/1"
READINESS_REPORT_SCHEMA = "testence/readiness-report/1"

SCHEMA_INVENTORY = MappingProxyType(
    {
        "evidence": EVIDENCE_SCHEMA,
        "planspec": PLAN_SCHEMA,
        "verdict": VERDICT_SCHEMA,
        "evidence_pack": EVIDENCE_PACK_SCHEMA,
        "pack_manifest": PACK_MANIFEST_SCHEMA,
        "run_manifest": RUN_MANIFEST_SCHEMA,
        "assurance_policy": ASSURANCE_POLICY_SCHEMA,
        "repair_proposal": REPAIR_SCHEMA,
        "ci_receipt": CI_RECEIPT_SCHEMA,
        "delivery_receipt": DELIVERY_RECEIPT_SCHEMA,
        "scaffold_manifest": SCAFFOLD_SCHEMA,
        "verdict_submission": SUBMISSION_SCHEMA,
        "engine_capabilities": CAPABILITY_SCHEMA,
        "quality_pack": QUALITY_PACK_SCHEMA,
        "quality_pack_lock": QUALITY_LOCK_SCHEMA,
        "quality_sync": QUALITY_SYNC_SCHEMA,
        "quality_summary": QUALITY_SUMMARY_SCHEMA,
        "correctness_corpus": CORPUS_REGISTRY_SCHEMA,
        "correctness_corpus_freeze": CORPUS_FREEZE_SCHEMA,
        "agent_install": AGENT_INSTALL_SCHEMA,
        "agent_install_receipt": AGENT_INSTALL_RECEIPT_SCHEMA,
        "demo_run": DEMO_RUN_SCHEMA,
        "release_manifest": RELEASE_MANIFEST_SCHEMA,
        "acceptance_receipt": ACCEPTANCE_RECEIPT_SCHEMA,
        "readiness_report": READINESS_REPORT_SCHEMA,
    }
)
