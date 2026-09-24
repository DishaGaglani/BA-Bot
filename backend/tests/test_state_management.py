"""Project state: structured state, legacy payload, PUT sync, gap analysis, prompts, summarisation."""
import json
import types

import pytest
import requests

import services.prompt_builder as prompt_builder
from models import DiscoverySection, Message, Project
from services.gap_analyzer import analyze_gaps, is_field_empty
from services.project_state_manager import (
    DEFAULT_STATE,
    get_legacy_payload,
    get_structured_state,
    save_structured_state,
    update_project_state,
)
from services.prompt_builder import build_optimized_prompt, estimate_tokens
from services.summary_manager import check_and_summarize
from tests.helpers import pending_fix, project_payload, seed_messages, unwrap


def _fresh(db, project):
    db.expire_all()
    return db.get(Project, project.id)


# ------------------------------------------------------------------ structured state
class TestStructuredState:
    def test_new_project_gets_full_default_state(self, make_user, make_project):
        state = get_structured_state(make_project(make_user()))
        assert set(state) == set(DEFAULT_STATE) and state["functional_requirements"] == []

    def test_stored_state_is_merged_over_defaults(self, make_user, make_project):
        project = make_project(make_user(), state={"project_name": "Stored", "custom_key": 1})
        state = get_structured_state(project)
        assert state["project_name"] == "Stored" and state["custom_key"] == 1
        assert state["budget"] == ""  # key missing from storage is filled from defaults

    @pytest.mark.parametrize("corrupt", ["not json", "[1, 2]", "null"])
    def test_corrupt_state_falls_back_to_defaults_instead_of_raising(self, db, make_user, make_project, corrupt):
        project = make_project(make_user())
        project.structured_state = corrupt
        db.commit()
        assert get_structured_state(project)["project_name"] == ""

    def test_save_and_reload_round_trip(self, db, make_user, make_project):
        project = make_project(make_user())
        state = get_structured_state(project)
        state["risks"] = ["vendor lock-in"]
        save_structured_state(db, project, state)
        assert get_structured_state(_fresh(db, project))["risks"] == ["vendor lock-in"]

    @pending_fix(
        "finding B",
        "get_structured_state returns a shallow copy of DEFAULT_STATE, so appending to a nested list "
        "(as update_project_state does for asked_questions) mutates the shared default and leaks into other projects",
    )
    def test_one_projects_state_never_leaks_into_another(self, db, make_user, make_project, llm):
        first, second = make_project(make_user()), make_project(make_user())
        update_project_state(db, first, "hi", "Who is the sponsor?")  # first has no stored state
        assert "Who is the sponsor?" not in get_structured_state(second)["asked_questions"]


# ------------------------------------------------------------------ update_project_state
class TestUpdateProjectState:
    @pytest.fixture
    def project(self, make_user, make_project):
        return make_project(make_user(), state=dict(DEFAULT_STATE))

    def test_applies_delta_and_persists(self, db, llm, project):
        llm.delta_text = json.dumps({"department": "Logistics", "budget": "50k"})
        update_project_state(db, project, "we are logistics", "Noted.")
        stored = json.loads(_fresh(db, project).structured_state)
        assert stored["department"] == "Logistics" and stored["budget"] == "50k"

    def test_recomputes_completed_sections_and_summary(self, db, llm, project):
        llm.delta_text = json.dumps(
            {
                "project_name": "Retail Hub",
                "functional_requirements": [{"title": "Login", "priority": "High", "confidence": 0.9}, {"title": "Reports"}],
                "non_functional_requirements": ["fast"],
                "risks": ["budget"],
            }
        )
        state = update_project_state(db, project, "x", "y")
        assert "Project Name" in state["completed_sections"]
        assert state["generated_summaries"] == (
            "Project Name: Retail Hub | Functional Reqs: Login, Reports | Non-Functional: fast | Risks: budget"
        )

    def test_extracts_and_deduplicates_questions_the_ai_asked(self, db, llm, project):
        reply = "Thanks. What is the budget? And who are the stakeholders?"
        update_project_state(db, project, "u", reply)
        update_project_state(db, project, "u", reply)
        asked = get_structured_state(_fresh(db, project))["asked_questions"]
        assert asked == ["What is the budget?", "And who are the stakeholders?"]

    def test_no_delta_still_saves_asked_questions_and_changes_nothing_else(self, db, llm, project):
        llm.delta_text = "{}"
        state = update_project_state(db, project, "u", "Anything else?")
        assert state["asked_questions"] == ["Anything else?"] and state["project_name"] == ""

    def test_llm_failure_does_not_lose_the_turn(self, db, llm, project):
        llm.nonstream_error = requests.ConnectionError("provider down")
        state = update_project_state(db, project, "u", "What is the timeline?")
        assert state["asked_questions"] == ["What is the timeline?"]

    def test_active_section_is_passed_to_the_extractor(self, db, llm, project):
        update_project_state(db, project, "u", "a", active_section="Stakeholders")
        assert "Stakeholders" in llm.calls[-1]["prompt"]

    @pending_fix("issue 7", "delta keys are merged into state without a schema, so hallucinated keys are persisted")
    def test_unknown_keys_from_the_model_are_not_persisted(self, db, llm, project):
        llm.delta_text = json.dumps({"department": "IT", "made_up_field": "junk"})
        update_project_state(db, project, "u", "a")
        stored = json.loads(_fresh(db, project).structured_state)
        assert stored["department"] == "IT" and "made_up_field" not in stored

    @pending_fix("issue 7", "the model can overwrite internally-managed bookkeeping such as asked_questions")
    def test_model_cannot_overwrite_internal_bookkeeping(self, db, llm, project):
        llm.delta_text = json.dumps({"asked_questions": ["forged"], "department": "IT"})
        state = update_project_state(db, project, "u", "Real question?")
        assert "forged" not in state["asked_questions"]

    @pending_fix("issue 7", "a bare string for a list field replaces the list and later renders one requirement per character")
    def test_bare_string_for_a_list_field_does_not_corrupt_state(self, db, llm, project):
        llm.delta_text = json.dumps({"functional_requirements": "SSO authentication required"})
        update_project_state(db, project, "u", "a")
        reqs = get_legacy_payload(_fresh(db, project))["functional_requirements"]
        assert [r["title"] for r in reqs] == ["SSO authentication required"]


# ------------------------------------------------------------------ legacy payload
class TestLegacyPayload:
    def test_shape_for_an_empty_project(self, make_user, make_project):
        payload = get_legacy_payload(make_project(make_user(), "Named"))
        assert payload["project"]["name"] == "Named"
        assert payload["functional_requirements"] == [] and payload["messages"] == []
        assert payload["status"] == "DRAFT" and payload["sessionId"]
        assert len(payload["missing_fields"]) == 9
        assert "Project Name" in payload["next_question"]

    def test_maps_state_onto_the_frontend_contract(self, make_user, make_project):
        state = dict(
            DEFAULT_STATE,
            project_name="Hub",
            department="Ops",
            sponsor="Ann",
            timeline="Q3",
            business_unit="Retail",
            stakeholders=["Ops", "IT"],
            budget="10k",
            constraints=["legal"],
            integrations=["SAP"],
            non_functional_requirements=["fast"],
            generated_summaries="summary",
        )
        payload = get_legacy_payload(make_project(make_user(), state=state))
        assert payload["project"] == {
            "name": "Hub", "department": "Ops", "sponsor": "Ann", "business_unit": "Retail", "expected_completion": "Q3",
        }
        assert payload["overview"]["stakeholders"] == ["Ops", "IT"]
        assert payload["discovery"]["budget"] == "10k" and payload["discovery"]["integrations"] == ["SAP"]
        assert payload["discovery"]["constraints"] == ["legal"] and payload["discovery"]["desired_outcomes"] == "summary"

    def test_business_unit_falls_back_to_industry(self, make_user, make_project):
        payload = get_legacy_payload(make_project(make_user(), state=dict(DEFAULT_STATE, industry="Retail")))
        assert payload["project"]["business_unit"] == "Retail"

    def test_functional_requirements_are_normalised(self, make_user, make_project):
        state = dict(DEFAULT_STATE, functional_requirements=[{"title": "A", "priority": "High", "confidence": 0.5}, {"title": "B"}, "C", 42])
        reqs = get_legacy_payload(make_project(make_user(), state=state))["functional_requirements"]
        assert reqs == [
            {"title": "A", "priority": "High", "confidence": 0.5},
            {"title": "B", "priority": "Medium", "confidence": 1.0},  # missing fields defaulted
            {"title": "C", "priority": "Medium", "confidence": 1.0},  # bare string accepted
        ]  # anything else is dropped rather than crashing

    def test_messages_are_returned_oldest_first(self, db, make_user, make_project):
        project = make_project(make_user())
        seed_messages(db, project, 4)
        payload = get_legacy_payload(_fresh(db, project))
        assert [m["text"] for m in payload["messages"]] == ["m0", "m1", "m2", "m3"]
        assert payload["messages"][0] == {"role": "user", "text": "m0"}

    def test_progress_is_reflected_in_missing_fields_and_next_question(self, make_user, make_project):
        state = {k: "x" for k in ("project_name", "industry", "stakeholders", "timeline", "budget",
                                  "functional_requirements", "non_functional_requirements", "integrations", "constraints")}
        payload = get_legacy_payload(make_project(make_user(), state=state))
        assert payload["missing_fields"] == [] and payload["next_question"] == "Discovery is complete!"

    def test_explicit_next_question_wins(self, make_user, make_project):
        payload = get_legacy_payload(make_project(make_user(), state=dict(DEFAULT_STATE, next_question="Custom?")))
        assert payload["next_question"] == "Custom?"


# ------------------------------------------------------------------ PUT /api/projects/{id} sync
class TestProjectUpdateSync:
    @pytest.fixture
    def setup(self, make_user, make_project, auth):
        owner = make_user()
        return owner, make_project(owner, "Before", session_id="session-original"), auth(owner)

    def test_frontend_fields_are_synced_into_structured_state(self, client, db, setup):
        _, project, headers = setup
        body = project_payload(
            "After",
            overview={"description": "d", "stakeholders": ["Ops", "IT"]},
            functional_requirements=[{"title": "Login", "priority": "High", "confidence": 0.9}],
        )
        body["project"].update(department="Ops", sponsor="Ann", expected_completion="Q4")
        assert client.put(f"/api/projects/{project.id}", headers=headers, json=body).status_code == 200

        fresh = _fresh(db, project)
        assert fresh.name == "After"
        state = get_structured_state(fresh)
        assert (state["project_name"], state["department"], state["sponsor"], state["timeline"]) == ("After", "Ops", "Ann", "Q4")
        assert state["stakeholders"] == ["Ops", "IT"]
        assert state["functional_requirements"] == [{"title": "Login", "priority": "High", "confidence": 0.9}]

    def test_response_reflects_the_saved_state(self, client, setup):
        _, project, headers = setup
        body = project_payload("Echo", functional_requirements=[{"title": "T", "priority": "Low", "confidence": 0.1}])
        data = unwrap(client.put(f"/api/projects/{project.id}", headers=headers, json=body))
        assert data["project"]["name"] == "Echo" and data["functional_requirements"][0]["title"] == "T"

    def test_existing_session_is_preserved_when_the_client_sends_a_different_one(self, client, db, setup):
        _, project, headers = setup
        client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload(sessionId="session-attacker"))
        assert _fresh(db, project).session_id == "session-original"

    @pending_fix(
        "finding C",
        "a PUT that omits sessionId rotates the project's session_id when project.data has none, "
        "orphaning the chat session",
    )
    def test_omitting_session_id_does_not_rotate_it(self, client, db, setup):
        _, project, headers = setup
        client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload())
        assert _fresh(db, project).session_id == "session-original"

    def test_reset_session_wipes_conversation_and_discovery_state(self, client, db, setup):
        _, project, headers = setup
        seed_messages(db, project, 4)
        project.summary, project.forjinn_session_id = "old summary", "forjinn-1"
        project.structured_state = json.dumps(dict(DEFAULT_STATE, functional_requirements=[{"title": "old"}]))
        db.commit()

        body = project_payload("Reset", resetSession=True, functional_requirements=[{"title": "ignored", "priority": "High", "confidence": 1}])
        assert client.put(f"/api/projects/{project.id}", headers=headers, json=body).status_code == 200

        fresh = _fresh(db, project)
        assert db.query(Message).filter_by(project_id=project.id).count() == 0
        assert fresh.summary is None and fresh.forjinn_session_id is None
        assert fresh.session_id != "session-original"
        state = get_structured_state(fresh)
        assert state["functional_requirements"] == [] and state["project_name"] == "Reset"


# ------------------------------------------------------------------ gap analysis
class TestGapAnalyzer:
    @pytest.mark.parametrize(
        "value,empty",
        [(None, True), ("", True), ("   ", True), ([], True), ("x", False), (["x"], False), ([{}], False), (0, False), ({}, False)],
    )
    def test_is_field_empty(self, value, empty):
        assert is_field_empty(value) is empty

    def test_empty_project_starts_at_the_first_section(self, db):
        result = analyze_gaps({}, db)
        assert result["current_section"] == "Project Name" and result["progress"] == 0
        assert len(result["missing_fields"]) == 9 and result["completed_fields"] == []

    def test_focus_moves_to_the_next_unanswered_section(self, db):
        assert analyze_gaps({"project_name": "X"}, db)["current_section"] == "Business Domain"

    def test_progress_is_the_rounded_percentage_of_completed_sections(self, db):
        result = analyze_gaps({"project_name": "X", "industry": "Y", "budget": "Z"}, db)
        assert result["progress"] == 33 and len(result["completed_fields"]) == 3

    def test_complete_project(self, db):
        keys = ("project_name", "industry", "stakeholders", "timeline", "budget", "functional_requirements",
                "non_functional_requirements", "integrations", "constraints")
        result = analyze_gaps({k: "x" for k in keys}, db)
        assert result == {"missing_fields": [], "completed_fields": result["completed_fields"],
                          "current_section": "Project Complete", "progress": 100}

    def test_sections_come_from_the_database_in_configured_order(self, db):
        db.add_all([
            DiscoverySection(section_key="budget", section_name="Money", prompt="p", question_order=2),
            DiscoverySection(section_key="project_name", section_name="Name It", prompt="p", question_order=1),
        ])
        db.commit()
        result = analyze_gaps({}, db)
        assert result["current_section"] == "Name It" and len(result["missing_fields"]) == 2

    def test_disabled_sections_are_ignored(self, db):
        db.add_all([
            DiscoverySection(section_key="project_name", section_name="Name", prompt="p", question_order=1, enabled=False),
            DiscoverySection(section_key="budget", section_name="Money", prompt="p", question_order=2),
        ])
        db.commit()
        assert analyze_gaps({}, db)["current_section"] == "Money"

    def test_a_section_is_not_targeted_before_its_prerequisites(self, db):
        """functional_requirements depends on industry, so industry is asked first even if ordered later."""
        db.add_all([
            DiscoverySection(section_key="functional_requirements", section_name="Features", prompt="p", question_order=1),
            DiscoverySection(section_key="industry", section_name="Domain", prompt="p", question_order=2),
        ])
        db.commit()
        assert analyze_gaps({}, db)["current_section"] == "Domain"
        assert analyze_gaps({"industry": "Retail"}, db)["current_section"] == "Features"


# ------------------------------------------------------------------ prompt building
class TestPromptBuilder:
    @pytest.fixture(autouse=True)
    def _no_settings_file(self, monkeypatch):
        real = prompt_builder.os
        stub = types.SimpleNamespace(path=types.SimpleNamespace(
            exists=lambda p: False, join=real.path.join, dirname=real.path.dirname, abspath=real.path.abspath))
        monkeypatch.setattr(prompt_builder, "os", stub)

    def _gaps(self, **overrides):
        gaps = {"completed_fields": ["Project Name"], "current_section": "Stakeholders", "missing_fields": ["Stakeholders"]}
        gaps.update(overrides)
        return gaps

    def _msg(self, role, text):
        return types.SimpleNamespace(role=role, text=text)

    def test_contains_system_prompt_state_and_the_latest_message(self):
        prompt = build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), None, [], "What now?")
        assert "expert Business Analyst" in prompt
        assert "Project Name: [COMPLETE]" in prompt and "Active Focus Section: Stakeholders" in prompt
        assert prompt.rstrip().endswith("User: What now?\n\nAI:")

    def test_only_the_last_two_messages_are_included(self):
        history = [self._msg("user" if i % 2 == 0 else "ai", f"HISTORY-{i}") for i in range(5)]
        prompt = build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), None, history, "q")
        assert "HISTORY-3" in prompt and "HISTORY-4" in prompt
        assert not any(f"HISTORY-{i}" in prompt for i in (0, 1, 2))

    def test_only_the_last_five_asked_questions_are_included(self):
        state = dict(DEFAULT_STATE, asked_questions=[f"ASKED-{i}?" for i in range(1, 8)])
        prompt = build_optimized_prompt(state, self._gaps(), None, [], "q")
        assert "ASKED-7?" in prompt and "ASKED-3?" in prompt
        assert "ASKED-2?" not in prompt and "ASKED-1?" not in prompt

    def test_running_summary_is_included_only_when_present(self):
        assert "RUNNING INTERVIEW SUMMARY" not in build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), None, [], "q")
        assert "the gist" in build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), "the gist", [], "q")

    def test_active_section_state_is_shown_but_other_sections_are_not(self):
        state = dict(DEFAULT_STATE, stakeholders=["Ops team"], budget="SECRET-BUDGET")
        prompt = build_optimized_prompt(state, self._gaps(), None, [], "q")
        assert "Ops team" in prompt and "SECRET-BUDGET" not in prompt

    def test_section_instructions_come_from_the_database(self, db):
        db.add(DiscoverySection(section_key="stakeholders", section_name="Stakeholders", prompt="ASK ABOUT WHO USES IT",
                                default_value="Employees", validation_rules="at least one group"))
        db.commit()
        prompt = build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), None, [], "q")
        assert "ASK ABOUT WHO USES IT" in prompt and "Employees" in prompt and "at least one group" in prompt

    def test_disabled_section_instructions_are_not_used(self, db):
        db.add(DiscoverySection(section_key="stakeholders", section_name="Stakeholders", prompt="HIDDEN", enabled=False))
        db.commit()
        assert "HIDDEN" not in build_optimized_prompt(dict(DEFAULT_STATE), self._gaps(), None, [], "q")

    def test_administrator_can_override_the_system_prompt(self, monkeypatch):
        real = prompt_builder.os
        stub = types.SimpleNamespace(path=types.SimpleNamespace(
            exists=lambda p: True, join=real.path.join, dirname=real.path.dirname, abspath=real.path.abspath))
        monkeypatch.setattr(prompt_builder, "os", stub)
        monkeypatch.setattr(prompt_builder, "open", lambda *a, **k: __import__("io").StringIO('{"systemPrompt": "BE BRIEF"}'), raising=False)
        assert prompt_builder.get_system_prompt() == "BE BRIEF"

    def test_token_estimate_is_four_characters_per_token(self):
        assert estimate_tokens("x" * 40) == 10 and estimate_tokens("") == 0


# ------------------------------------------------------------------ rolling summarisation
class TestSummaryManager:
    @pytest.fixture
    def project(self, make_user, make_project):
        return make_project(make_user())

    def test_below_threshold_does_nothing_and_never_calls_the_model(self, db, llm, project):
        seed_messages(db, project, 9)
        assert check_and_summarize(db, project) is False
        assert llm.calls == []

    def test_summarises_older_messages_and_keeps_the_last_five_live(self, db, llm, project):
        seed_messages(db, project, 12)
        llm.summary_text = "  Fresh summary  "
        assert check_and_summarize(db, project) is True

        fresh = _fresh(db, project)
        assert fresh.summary == "Fresh summary"
        archived = {m.text for m in db.query(Message).filter_by(project_id=project.id, is_archived=True)}
        live = {m.text for m in db.query(Message).filter_by(project_id=project.id, is_archived=False)}
        assert archived == {f"m{i}" for i in range(7)} and live == {f"m{i}" for i in range(7, 12)}

    def test_previous_summary_is_carried_into_the_next_one(self, db, llm, project):
        project.summary = "EARLIER-SUMMARY"
        db.commit()
        seed_messages(db, project, 10)
        check_and_summarize(db, project)
        prompt = llm.calls[-1]["prompt"]
        assert "EARLIER-SUMMARY" in prompt and "m0" in prompt and "m9" not in prompt  # newest five stay raw

    def test_model_failure_leaves_everything_untouched(self, db, llm, project):
        seed_messages(db, project, 12)
        llm.nonstream_error = requests.ConnectionError("down")
        assert check_and_summarize(db, project) is False
        assert _fresh(db, project).summary is None
        assert db.query(Message).filter_by(project_id=project.id, is_archived=True).count() == 0

    def test_empty_model_response_is_not_treated_as_success(self, db, llm, project):
        seed_messages(db, project, 12)
        llm.summary_text = ""
        assert check_and_summarize(db, project) is False
        assert db.query(Message).filter_by(project_id=project.id, is_archived=True).count() == 0
