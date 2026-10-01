"""Synthetic FTD ADR fixtures over the public `saas-accounts` pack: a change corpus (a formal
approved ADR, a rough meeting note, a binary diagram) and the analysis / procedures a model
would submit for it. Generic, invented content only."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import adr  # noqa: E402
from expansion import DIMENSIONS  # noqa: E402
from support import PackRun  # noqa: E402

ADR_FILE = "adr-007-invitation-window.md"
ADR_TEXT = """# ADR-007 Invitation expiry window

Status: Accepted by the account product owner on 2026-09-20.

Decision: an invitation now expires 3 days after it was sent. This replaces the previous 7-day window.

Invitations already sent before the decision keep their original 7-day window.
"""
NOTE_FILE = "notes/team-sync.txt"
NOTE_TEXT = """Team sync notes

Maybe we should remind the owner one day before an invitation expires.
Open point: does resending an invitation restart the expiry window?
"""


def write_corpus(folder: Path, *, with_note: bool = True, with_binary: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ADR_FILE).write_text(ADR_TEXT, encoding="utf-8")
    if with_note:
        (folder / NOTE_FILE).parent.mkdir(parents=True, exist_ok=True)
        (folder / NOTE_FILE).write_text(NOTE_TEXT, encoding="utf-8")
    if with_binary:
        (folder / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
    return folder


def reviews(decision: str, special: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every expansion dimension reviewed once for a behavior-changing decision."""
    result = []
    for dimension in DIMENSIONS:
        item = special.get(dimension) or {"disposition": "NOT_APPLICABLE",
                                          "reason": "the expiry window change does not touch this dimension"}
        result.append({"decision": decision, "dimension": dimension, **item})
    return result


def analysis() -> dict[str, Any]:
    return copy.deepcopy({
        "sources": [
            {"path": ADR_FILE, "document_status": "APPROVED_DECISION",
             "summary": "Formal decision that shortens the invitation expiry window."},
            {"path": NOTE_FILE, "document_status": "MIXED_CONTENT",
             "summary": "Rough meeting note with a proposal and an open point about invitations."},
        ],
        "statements": [
            {"key": "S1", "source": ADR_FILE, "reference": "Decision paragraph",
             "excerpt": "an invitation now expires 3 days after it was sent", "kind": "REQUIREMENT_CHANGE",
             "status": "APPROVED", "authority_evidence": "Status: Accepted by the account product owner",
             "meaning": "The invitation validity window becomes three days.", "concepts": ["invitation", "expiry"],
             "candidate_concepts": ["REQ-001"], "confidence": "HIGH", "disposition": "DECISION"},
            {"key": "S2", "source": ADR_FILE, "reference": "Last paragraph",
             "excerpt": "Invitations already sent before the decision keep their original 7-day window.",
             "kind": "MIGRATION_CONCERN", "status": "APPROVED",
             "authority_evidence": "Status: Accepted by the account product owner",
             "meaning": "Invitations sent earlier still expire after seven days.", "concepts": ["invitation"],
             "candidate_concepts": ["REQ-001"], "confidence": "HIGH", "disposition": "DECISION"},
            {"key": "S3", "source": NOTE_FILE, "reference": "line 3",
             "excerpt": "Maybe we should remind the owner one day before an invitation expires.",
             "kind": "PROPOSAL", "status": "PROPOSED", "meaning": "A possible reminder before expiry.",
             "confidence": "LOW", "disposition": "CONTEXT",
             "reason": "an undecided idea that defines no behavior to test"},
            {"key": "S4", "source": NOTE_FILE, "reference": "line 4",
             "excerpt": "does resending an invitation restart the expiry window?", "kind": "OPEN_QUESTION",
             "status": "UNCERTAIN", "meaning": "Whether a resend restarts the window is unknown.",
             "confidence": "MEDIUM", "disposition": "QUESTION"},
        ],
        "decisions": [
            {"key": "D1", "official_id": "ADR-007", "statements": ["S1", "S2"], "relationship": "SUPERSEDES",
             "statement": "An invitation expires three days after it was sent; invitations sent before the decision keep seven days.",
             "affected_behavior": "invitation expiry window",
             "previous_authority": {"requirements": ["REQ-001"], "statement": "The invitation expires after 7 days."},
             "related_requirements": ["REQ-001", "REQ-002"], "related_test_cases": ["TC-002", "TC-004"],
             "claims": [
                 {"claim": "An invitation sent after the decision is expired once three days have passed.",
                  "disposition": "COVERED_BY_UPDATE", "cases": ["TC-002"]},
                 {"claim": "An invitation sent before the decision is still valid four days after it was sent.",
                  "disposition": "NEW_TEST", "cases": ["N1"]},
                 {"claim": "An expired invitation cannot be accepted.", "disposition": "COVERED_BY_EXISTING",
                  "cases": ["TC-004"]},
             ]},
            {"key": "D2", "statements": ["S4"], "relationship": "UNCLEAR",
             "statement": "It is unknown whether resending an invitation restarts the expiry window.",
             "affected_behavior": "invitation resend"},
        ],
        "test_cases": [
            {"test": "TC-002", "action": "UPDATE", "impact": "DIRECT", "decisions": ["D1"],
             "reason": "The approved decision shortens the expiry window from seven to three days.",
             "design": {"title": "Invitation expires after three days", "family": "Invitations",
                        "objective": "Verify that an invitation becomes expired three days after it was sent.",
                        "actor": "invited user", "state": "an invitation sent four days ago, after the decision",
                        "trigger": "open the invitation link", "expected": "The invitation status is expired because more than 3 days passed.",
                        "failure_domain": "invitation expiry", "priority": "MEDIUM",
                        "priority_reason": "Stale invitations must not grant access.", "primary_type": "BOUNDARY",
                        "basis": "ACCEPTANCE"}},
            {"key": "N1", "action": "CREATE", "impact": "DIRECT", "decisions": ["D1"],
             "reason": "Invitations sent before the decision keep the previous window, which no Test Case covers.",
             "design": {"title": "Earlier invitation keeps the seven-day window", "family": "Invitations",
                        "objective": "Verify that an invitation sent before the decision is still valid after four days.",
                        "actor": "invited user", "state": "an invitation sent four days ago, before the decision",
                        "trigger": "open the invitation link", "expected": "The invitation status is valid because the 7-day window still applies.",
                        "failure_domain": "legacy invitation expiry", "priority": "MEDIUM",
                        "priority_reason": "Earlier invitations must not expire early.", "primary_type": "BOUNDARY",
                        "basis": "DERIVED", "dimension": "BOUNDARY"}},
            {"test": "TC-004", "action": "AFFECTED_NO_CHANGE", "impact": "INDIRECT", "decisions": ["D1"],
             "reason": "An expired invitation is still rejected; only the window length changed."},
            {"test": "TC-012", "action": "REVIEW_ONLY", "impact": "INDIRECT", "decisions": ["D2"],
             "reason": "The onboarding journey may resend an invitation, whose effect on the window is unknown."},
        ],
        "dimension_reviews": reviews("D1", {
            "BOUNDARY": {"disposition": "MATERIALIZED", "cases": ["TC-002", "N1"]},
            "NEGATIVE": {"disposition": "ALREADY_COVERED", "cases": ["TC-004"]},
            "E2E": {"disposition": "QUESTION_REQUIRED", "question": "Q1"},
        }),
        "questions": [
            {"key": "Q1", "question": "Does resending an invitation restart its expiry window?",
             "reason": "The meeting note leaves the effect of a resend on the new window open.",
             "impact": "EXPECTED_RESULT", "blocking": False, "decisions": ["D2"], "statements": ["S4"],
             "requirements": ["REQ-001"], "tests": ["TC-012"]},
        ],
        "findings": [
            {"key": "F1", "type": "INFORMATION",
             "statement": "Two expiry windows coexist until every earlier invitation has expired.",
             "decisions": ["D1"], "statements": ["S2"], "tests": ["TC-002", "N1"],
             "source_refs": [{"source": ADR_FILE, "reference": "Last paragraph"}]},
        ],
    })


def procedures() -> dict[str, Any]:
    evidence = [{"source": ADR_FILE, "reference": "Decision paragraph"}]
    return copy.deepcopy({"procedures": [
        {"test": "TC-002",
         "preconditions": ["An invitation for EMAIL_RECENT was sent to ACCOUNT_A four days ago, after the decision."],
         "test_data": [{"name": "EMAIL_RECENT", "description": "invited address whose invitation is four days old"},
                       {"name": "ACCOUNT_A", "description": "account with free seats below its seat limit"}],
         "steps": [{"action": "Open the invitation link received by EMAIL_RECENT.", "expected_result": "The invitation page loads."},
                   {"action": "Check the invitation status shown.",
                    "expected_result": "The invitation status is expired because more than 3 days passed."}],
         "evidence_refs": evidence, "automation": {"suitability": "MEDIUM", "layer": "UI", "tool_hint": "NONE"},
         "unknowns": [{"kind": "MISSING_FIXTURE", "detail": "a clock or seeded invitation date is needed to automate the age"}]},
        {"test": "N1",
         "preconditions": ["An invitation for EMAIL_LEGACY was sent to ACCOUNT_A four days ago, before the decision."],
         "test_data": [{"name": "EMAIL_LEGACY", "description": "invited address whose invitation predates the decision"},
                       {"name": "ACCOUNT_A", "description": "account with free seats below its seat limit"}],
         "steps": [{"action": "Open the invitation link received by EMAIL_LEGACY.", "expected_result": "The invitation page loads."},
                   {"action": "Check the invitation status shown.",
                    "expected_result": "The invitation status is valid because the 7-day window still applies."}],
         "evidence_refs": [{"source": ADR_FILE, "reference": "Last paragraph"}],
         "automation": {"suitability": "MEDIUM", "layer": "UI", "tool_hint": "NONE"},
         "unknowns": [{"kind": "MISSING_FIXTURE", "detail": "a seeded invitation date before the decision is needed"}]},
    ]})


ROUND2_FILE = "adr-008-legacy-cutoff.md"
ROUND2_TEXT = """# ADR-008 Legacy invitation cutoff

Status: Approved by the account product owner.

Invitations sent before ADR-007 stay valid only until 2026-10-15.

An owner can resend an expired invitation; the resent invitation gets a new 3-day window.
"""
ROUND3_FILE = "adr-009-seat-check.md"
ROUND3_TEXT = """# ADR-009 Seat check moves to acceptance

Status: Accepted.

Invitations are no longer checked against the seat limit when they are sent; the seat limit is checked when an invitation is accepted.
"""


def _design(title, objective, state, expected, domain, primary, basis="ACCEPTANCE", trigger="open the invitation link",
            actor="invited user", priority_reason="Access must follow the approved decision.", **extra):
    return {"title": title, "family": "Invitations", "objective": objective, "actor": actor, "state": state,
            "trigger": trigger, "expected": expected, "failure_domain": domain, "priority": "MEDIUM",
            "priority_reason": priority_reason, "primary_type": primary, "basis": basis, **extra}


def _procedure(test, fixture, precondition, steps, evidence, unknowns=None, **extra):
    return {"test": test, "preconditions": [precondition],
            "test_data": [{"name": fixture, "description": "invited address used by this Test Case"},
                          {"name": "ACCOUNT_A", "description": "account with free seats below its seat limit"}],
            "steps": [{"action": a, "expected_result": e} for a, e in steps], "evidence_refs": evidence,
            "automation": {"suitability": "MEDIUM", "layer": "UI", "tool_hint": "NONE"},
            "unknowns": unknowns if unknowns is not None else
            [{"kind": "MISSING_FIXTURE", "detail": "a seeded invitation date is needed to automate the age"}], **extra}


def round2_analysis() -> dict[str, Any]:
    return {
        "sources": [{"path": ROUND2_FILE, "document_status": "APPROVED_DECISION",
                     "summary": "Formal decision that ends the legacy window and defines resending."}],
        "statements": [
            {"key": "S1", "source": ROUND2_FILE, "reference": "second paragraph",
             "excerpt": "Invitations sent before ADR-007 stay valid only until 2026-10-15.", "kind": "REQUIREMENT_CHANGE",
             "status": "APPROVED", "authority_evidence": "Status: Approved by the account product owner.",
             "meaning": "The legacy seven-day window ends on a fixed date.", "confidence": "HIGH", "disposition": "DECISION"},
            {"key": "S2", "source": ROUND2_FILE, "reference": "third paragraph",
             "excerpt": "the resent invitation gets a new 3-day window", "kind": "BUSINESS_RULE", "status": "APPROVED",
             "authority_evidence": "Status: Approved by the account product owner.",
             "meaning": "Resending an expired invitation starts a fresh three-day window.", "confidence": "HIGH",
             "disposition": "DECISION"},
        ],
        "decisions": [
            {"key": "D1", "official_id": "ADR-008", "statements": ["S1"], "relationship": "CHANGES",
             "statement": "Invitations sent before ADR-007 stay valid only until a fixed cutoff date.",
             "affected_behavior": "legacy invitation expiry",
             "previous_authority": {"decisions": ["ADR-007"],
                                    "statement": "Invitations sent before the decision keep their original 7-day window."},
             "claims": [{"claim": "An earlier invitation is still valid before the cutoff date.",
                         "disposition": "COVERED_BY_UPDATE", "cases": ["TC-013"]}]},
            {"key": "D2", "statements": ["S2"], "relationship": "ADDS_BEHAVIOR",
             "statement": "Resending an expired invitation gives it a new three-day window.",
             "affected_behavior": "invitation resend", "related_requirements": ["REQ-001"],
             "claims": [{"claim": "A resent invitation is valid during its new three-day window.",
                         "disposition": "NEW_TEST", "cases": ["N2"]}]},
        ],
        "test_cases": [
            {"test": "TC-013", "action": "UPDATE", "impact": "DIRECT", "decisions": ["D1"],
             "reason": "The legacy window now ends on the cutoff date.",
             "design": _design("Earlier invitation stays valid before the cutoff",
                               "Verify that an invitation sent before ADR-007 is valid before the cutoff date.",
                               "an invitation sent four days ago, before ADR-007, with the cutoff date not reached",
                               "The invitation status is valid because the 2026-10-15 cutoff has not passed.",
                               "legacy invitation cutoff", "BOUNDARY", basis="DERIVED", dimension="BOUNDARY")},
            {"key": "N2", "action": "CREATE", "impact": "DIRECT", "decisions": ["D2"],
             "reason": "Resending an expired invitation is new behavior that no Test Case covers.",
             "design": _design("Resent invitation gets a new window",
                               "Verify that a resent invitation is valid during its new three-day window.",
                               "an invitation that expired and was resent by the owner one day ago",
                               "The invitation status is valid because the resent invitation has a new 3-day window.",
                               "invitation resend window", "STATE_TRANSITION", basis="DERIVED", dimension="STATE_TRANSITION")},
        ],
        "dimension_reviews": [*reviews("D1", {"BOUNDARY": {"disposition": "MATERIALIZED", "cases": ["TC-013"]}}),
                              *reviews("D2", {"STATE_TRANSITION": {"disposition": "MATERIALIZED", "cases": ["N2"]}})],
        "question_dispositions": [{"question": "Q-003", "disposition": "RESOLVED_BY_ADR", "decision": "D2",
                                   "reason": "The decision states that a resend starts a new window."}],
    }


def round2_procedures() -> dict[str, Any]:
    evidence = [{"source": ROUND2_FILE, "reference": "second paragraph"}]
    return {"procedures": [
        _procedure("TC-013", "EMAIL_LEGACY", "An invitation for EMAIL_LEGACY was sent to ACCOUNT_A four days ago, before ADR-007.",
                   [("Open the invitation link received by EMAIL_LEGACY.", "The invitation page loads."),
                    ("Check the invitation status shown.",
                     "The invitation status is valid because the 2026-10-15 cutoff has not passed.")], evidence),
        _procedure("N2", "EMAIL_RESENT", "The owner of ACCOUNT_A resent the expired invitation of EMAIL_RESENT one day ago.",
                   [("Open the resent invitation link received by EMAIL_RESENT.", "The invitation page loads."),
                    ("Check the invitation status shown.",
                     "The invitation status is valid because the resent invitation has a new 3-day window.")],
                   [{"source": ROUND2_FILE, "reference": "third paragraph"}]),
    ]}


def round3_analysis() -> dict[str, Any]:
    return {
        "sources": [{"path": ROUND3_FILE, "document_status": "APPROVED_DECISION",
                     "summary": "Formal decision that moves the seat check from sending to accepting."}],
        "statements": [{"key": "S1", "source": ROUND3_FILE, "reference": "second paragraph",
                        "excerpt": "the seat limit is checked when an invitation is accepted",
                        "kind": "STATE_OR_WORKFLOW_CHANGE", "status": "APPROVED", "authority_evidence": "Status: Accepted.",
                        "meaning": "Sending no longer checks seats; accepting does.", "confidence": "HIGH",
                        "disposition": "DECISION"}],
        "decisions": [{"key": "D1", "official_id": "ADR-009", "statements": ["S1"], "relationship": "SUPERSEDES",
                       "statement": "The seat limit is checked when an invitation is accepted, not when it is sent.",
                       "affected_behavior": "seat limit enforcement",
                       "previous_authority": {"requirements": ["REQ-003"],
                                              "statement": "An invitation that would exceed the limit is rejected."},
                       "claims": [{"claim": "Accepting an invitation beyond the seat limit is rejected.",
                                   "disposition": "NEW_TEST", "cases": ["N3"]},
                                  {"claim": "Simultaneous acceptances never exceed the seat limit.",
                                   "disposition": "COVERED_BY_EXISTING", "cases": ["TC-010"]}]}],
        "test_cases": [
            {"test": "TC-005", "action": "SUPERSEDE", "impact": "DIRECT", "decisions": ["D1"], "superseded_by": "N3",
             "reason": "Rejecting the invitation itself is no longer the expected behavior."},
            {"key": "N3", "action": "CREATE", "impact": "DIRECT", "decisions": ["D1"], "supersedes": "TC-005",
             "reason": "The seat limit is now enforced when the invitation is accepted.",
             "design": _design("Acceptance beyond the seat limit is rejected",
                               "Verify that accepting an invitation is rejected when no seat is free.",
                               "an account whose active members already fill its seat limit",
                               'The acceptance is rejected with the message "No seats available".',
                               "seat limit at acceptance", "NEGATIVE", trigger="accept the invitation")},
            {"test": "TC-010", "action": "AFFECTED_NO_CHANGE", "impact": "INDIRECT", "decisions": ["D1"],
             "reason": "Concurrent acceptances were already limited at acceptance time."},
        ],
        "dimension_reviews": reviews("D1", {"NEGATIVE": {"disposition": "MATERIALIZED", "cases": ["N3"]},
                                            "CONCURRENCY": {"disposition": "ALREADY_COVERED", "cases": ["TC-010"]}}),
    }


def round3_procedures() -> dict[str, Any]:
    return {"procedures": [{
        "test": "N3", "preconditions": ["ACCOUNT_FULL has no free seat and EMAIL_LATE holds a pending invitation to it."],
        "test_data": [{"name": "ACCOUNT_FULL", "description": "account whose active members fill its seat limit"},
                      {"name": "EMAIL_LATE", "description": "invited address with a pending invitation"}],
        "steps": [{"action": "Open the invitation link received by EMAIL_LATE.", "expected_result": "The invitation page loads."},
                  {"action": "Accept the invitation.",
                   "expected_result": 'The acceptance is rejected with the message "No seats available".'}],
        "evidence_refs": [{"source": ROUND3_FILE, "reference": "second paragraph"}],
        "automation": {"suitability": "HIGH", "layer": "UI", "tool_hint": "PLAYWRIGHT"}}]}


def empty_analysis() -> dict[str, Any]:
    return {}


class AdrRun:
    """A finalized synthetic canonical run plus helpers to drive ADR rounds over it."""

    def __init__(self, pack: str = "saas-accounts"):
        self.pack = PackRun(pack)
        self.pack.finalize()
        self.run_dir = self.pack.run_dir
        self.artifacts = self.pack.artifacts
        self.corpus = self.pack.root / "docs" / "adr"

    def round(self, analysis_payload=None, procedures_payload=None, **start) -> dict[str, Any]:
        started = adr.start_adr(self.run_dir, self.corpus, **start)
        adr_id = started["adr_run_id"]
        adr.submit_analysis(self.run_dir, adr_id, analysis() if analysis_payload is None else analysis_payload)
        adr.submit_procedures(self.run_dir, adr_id, procedures() if procedures_payload is None else procedures_payload)
        return {"start": started, **adr.finalize_adr(self.run_dir, adr_id)}

    def close(self) -> None:
        self.pack.close()
