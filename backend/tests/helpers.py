import pytest


def pending_fix(issue: str, reason: str):
    """Mark a test that asserts correct behavior which is only true once a
    specific fix is merged.

    strict=True is deliberate: when that fix lands the test starts passing, which
    pytest reports as a failure (XPASS), forcing whoever merged it to delete the
    marker. Without strict, stale markers would silently hide future regressions.
    """
    return pytest.mark.xfail(
        strict=True,
        reason=f"[{issue}] {reason}. Remove this marker once that fix is merged.",
    )


def seed_messages(db, project, count, *, archived_upto=0):
    """Insert `count` alternating user/ai messages with strictly increasing timestamps."""
    import datetime

    from models import Message

    base = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    for i in range(count):
        db.add(
            Message(
                project_id=project.id,
                role="user" if i % 2 == 0 else "ai",
                text=f"m{i}",
                is_archived=i < archived_upto,
                created_at=base + datetime.timedelta(seconds=i),
            )
        )
    db.commit()


def unwrap(response):
    """The response middleware wraps successful JSON as {success, data, message}."""
    body = response.json()
    if isinstance(body, dict) and body.get("success") is True and "data" in body:
        return body["data"]
    return body


def project_payload(name="Test Project", **overrides):
    """A valid body for POST/PUT /api/projects."""
    payload = {
        "project": {
            "name": name,
            "department": "IT",
            "sponsor": "Sponsor",
            "business_unit": "Retail",
            "expected_completion": "6 months",
        },
        "overview": {"description": "desc", "stakeholders": ["Ops"]},
        "discovery": {
            "business_problem": "problem",
            "business_goals": "goals",
            "desired_outcomes": "outcomes",
            "constraints": [],
            "budget": "10k",
            "integrations": [],
            "non_functional_requirements": [],
        },
        "functional_requirements": [],
        "missing_fields": [],
        "next_question": "",
    }
    payload.update(overrides)
    return payload
