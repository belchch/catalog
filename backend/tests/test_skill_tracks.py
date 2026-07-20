from __future__ import annotations

from app.api.skills import (
    BUILD_SKILL_SYSTEM_PROMPT,
    PROPOSE_SKILL_TRACKS_SYSTEM_PROMPT,
    TRACK_INTENT_PREFIX,
    _ASSISTANT_JOURNAL_MARK,
    _USER_INTENT_MARK,
)
from app.llm.base import CompletionResult, ToolCall
from app.skills.repo_skill import get_skill
from app.storage.repo_message import add_message, list_messages


def _completion(
    content: str | None = None, *, tool_calls: list[ToolCall] | None = None
) -> CompletionResult:
    return CompletionResult(
        content=content,
        tool_calls=list(tool_calls or []),
        finish_reason="stop",
    )


def _track(
    *,
    name: str = "Сравнение по топикам",
    description: str = "Сравнивает документы по общим темам",
    operation: str = "сравнить документы по топикам",
    input_arity: int | None = 2,
    rationale: str = "Пользователь явно просит сравнение по темам",
) -> dict:
    return {
        "name": name,
        "description": description,
        "operation": operation,
        "input_arity": input_arity,
        "rationale": rationale,
    }


def _propose_call(tracks: list[dict]) -> ToolCall:
    return ToolCall(
        id="tracks-1",
        name="propose_skill_tracks",
        arguments={"tracks": tracks},
    )


def _build_call(
    *,
    name: str = "Сравнение по топикам",
    description: str = "Сравнивает два документа по общим темам",
    system_prompt: str = "Сравни входные документы по темам и выдай различия.",
    input_arity: int | None = 2,
) -> ToolCall:
    return ToolCall(
        id="build-1",
        name="build_skill",
        arguments={
            "name": name,
            "description": description,
            "kind": "agent",
            "system_prompt": system_prompt,
            "allowed_tools": ["read_document"],
            "model": "test/model",
            "verify_checks": [{"check": "non_empty"}],
            "input_arity": input_arity,
            "non_determinism_reason": "нужно суждение о темах",
        },
    )


def test_anti_domain_prompts_contain_rules_and_few_shot() -> None:
    for prompt in (BUILD_SKILL_SYSTEM_PROMPT, PROPOSE_SKILL_TRACKS_SYSTEM_PROMPT):
        assert "операция" in prompt.lower() or "операци" in prompt
        assert "Go" in prompt and "Dart" in prompt
        assert TRACK_INTENT_PREFIX in prompt


def test_propose_skill_tracks_returns_one_to_three(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(
        db,
        session_id=session_id,
        role="user",
        content="Сравни эти два файла по топикам",
    )
    tracks = [
        _track(),
        _track(
            name="Краткое резюме каждого",
            description="Суммирует каждый документ отдельно",
            operation="суммировать каждый документ",
            input_arity=None,
            rationale="Возможно, нужна сводка, а не сравнение",
        ),
    ]
    provider.script = [_completion(tool_calls=[_propose_call(tracks)])]

    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] is False
    assert body["fallback"] is False
    assert len(body["tracks"]) == 2
    assert body["tracks"][0]["name"] == "Сравнение по топикам"
    assert body["tracks"][0]["input_arity"] == 2


def test_propose_skill_tracks_three_tracks(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(db, session_id=session_id, role="user", content="Что-то с документами")
    tracks = [
        _track(name="A", operation="op A", rationale="r A"),
        _track(name="B", operation="op B", rationale="r B", input_arity=1),
        _track(name="C", operation="op C", rationale="r C", input_arity=None),
    ]
    provider.script = [_completion(tool_calls=[_propose_call(tracks)])]
    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200
    assert len(resp.json()["tracks"]) == 3


def test_propose_skill_tracks_retry_then_success(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(db, session_id=session_id, role="user", content="Сравни доки")
    bad = _completion(content="без tool call")
    good = _completion(tool_calls=[_propose_call([_track()])])
    provider.script = [bad, good]

    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fallback"] is False
    assert len(body["tracks"]) == 1
    assert len(provider.requests) == 2


def test_propose_skill_tracks_invalid_then_fallback(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(db, session_id=session_id, role="user", content="Сравни доки")
    empty_tracks = _completion(
        tool_calls=[
            ToolCall(
                id="t1",
                name="propose_skill_tracks",
                arguments={"tracks": []},
            )
        ]
    )
    provider.script = [empty_tracks, empty_tracks, empty_tracks]

    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tracks"] == []
    assert body["fallback"] is True
    assert body["skipped"] is False


def test_propose_skill_tracks_edit_session_skipped(client, db) -> None:
    from app.skills.config import SkillConfig
    from app.skills.repo_skill import create_skill

    sid = create_skill(
        db,
        name="Existing",
        description="d",
        config=SkillConfig(
            name="Existing",
            description="d",
            system_prompt="p",
            allowed_tools=["read_document"],
            model="test/model",
        ),
        status="committed",
    )
    edit = client.post(f"/skills/{sid}/edit")
    assert edit.status_code == 200
    session_id = edit.json()["session_id"]

    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] is True
    assert body["tracks"] == []
    assert body["fallback"] is False


def test_select_skill_track_appends_user_message_without_planner(
    client, db
) -> None:
    session_id = client.post("/sessions").json()["id"]
    track = _track()
    resp = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": track},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["content"].startswith(TRACK_INTENT_PREFIX)
    assert "сравнить документы по топикам" in body["content"]

    msgs = list_messages(db, session_id)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == body["content"]


def test_select_skill_track_edit_session_rejected(client, db) -> None:
    from app.skills.config import SkillConfig
    from app.skills.repo_skill import create_skill

    sid = create_skill(
        db,
        name="Existing",
        description="d",
        config=SkillConfig(
            name="Existing",
            description="d",
            system_prompt="p",
            allowed_tools=["read_document"],
            model="test/model",
        ),
        status="committed",
    )
    edit = client.post(f"/skills/{sid}/edit")
    assert edit.status_code == 200
    session_id = edit.json()["session_id"]

    resp = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track()},
    )
    assert resp.status_code == 400, resp.text
    assert "edit session" in resp.json()["detail"]
    msgs = list_messages(db, session_id)
    assert not any(
        m["role"] == "user"
        and isinstance(m["content"], str)
        and m["content"].startswith(TRACK_INTENT_PREFIX)
        for m in msgs
    )


def test_select_skill_track_idempotent_when_intent_exists(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    first = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track()},
    )
    assert first.status_code == 200, first.text
    content = first.json()["content"]

    second = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track(name="Другой", operation="другая операция")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["content"] == content
    msgs = [
        m
        for m in list_messages(db, session_id)
        if m["role"] == "user"
        and isinstance(m["content"], str)
        and m["content"].startswith(TRACK_INTENT_PREFIX)
    ]
    assert len(msgs) == 1


def test_propose_skill_tracks_skips_when_track_intent_exists(
    client, provider, db
) -> None:
    session_id = client.post("/sessions").json()["id"]
    select = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track()},
    )
    assert select.status_code == 200, select.text

    provider.script = [
        _completion(tool_calls=[_propose_call([_track(name="ShouldNotRun")])])
    ]
    resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] is True
    assert body["tracks"] == []
    assert body["fallback"] is False
    assert provider.requests == []


def test_skill_track_rejects_input_arity_above_two(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track(input_arity=3)},
    )
    assert resp.status_code == 422, resp.text


def test_build_without_skill_tracks_still_works(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(db, session_id=session_id, role="user", content="Хочу саммаризатор")
    provider.script = [_completion(tool_calls=[_build_call(name="Summarizer", input_arity=1)])]
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["name"] == "Summarizer"


def test_build_with_track_intent_skips_artifact_pack(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "GoDartReview",
            "description": "ревью Go и Dart",
            "kind": "agent",
            "allowed_tools": ["read_document"],
            "verify_checks": [{"check": "non_empty"}],
            "input_arity": 1,
        },
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/prompt",
        json={"content": "Сделай code review для Go и Dart."},
    )
    select = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track()},
    )
    assert select.status_code == 200

    provider.script = [
        _completion(
            tool_calls=[
                _build_call(
                    name="Сравнение по топикам",
                    description="Сравнивает два документа по общим темам",
                    system_prompt="Сравни документы по темам без привязки к языку.",
                    input_arity=2,
                )
            ]
        )
    ]
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert len(provider.requests) == 1
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.name == "Сравнение по топикам"
    assert skill.config.input_arity == 2
    assert "Go" not in skill.config.name
    assert "Dart" not in skill.config.name
    assert "Go" not in skill.config.description
    assert "Dart" not in skill.config.description
    assert "Go" not in skill.config.system_prompt
    assert "Dart" not in skill.config.system_prompt


def test_build_history_annotated_in_memory(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(
        db,
        session_id=session_id,
        role="user",
        content="Вот код на Go и Dart, сравни по топикам",
    )
    add_message(
        db,
        session_id=session_id,
        role="assistant",
        content="Вижу Go-пакеты и Dart-виджеты, могу сделать ревью",
    )
    client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={"track": _track()},
    )
    provider.script = [_completion(tool_calls=[_build_call()])]
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text

    req_messages = provider.requests[0]["messages"]
    user_contents = [
        m.content for m in req_messages if m.role == "user" and m.content
    ]
    assistant_contents = [
        m.content for m in req_messages if m.role == "assistant" and m.content
    ]
    assert any(c.startswith(_USER_INTENT_MARK) for c in user_contents)
    assert any(c.startswith(_ASSISTANT_JOURNAL_MARK) for c in assistant_contents)

    persisted = list_messages(db, session_id)
    for m in persisted:
        if m["content"]:
            assert not m["content"].startswith(_USER_INTENT_MARK)
            assert not m["content"].startswith(_ASSISTANT_JOURNAL_MARK)


def test_fallback_phase_a_does_not_block_build(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    add_message(db, session_id=session_id, role="user", content="Сделай скилл")
    bad = _completion(content="нет")
    provider.script = [bad, bad, bad]
    tracks_resp = client.post(f"/sessions/{session_id}/skill-tracks")
    assert tracks_resp.json()["fallback"] is True

    provider.script = [_completion(tool_calls=[_build_call(name="Plain", input_arity=1)])]
    build_resp = client.post(f"/sessions/{session_id}/skills")
    assert build_resp.status_code == 200, build_resp.text
    assert build_resp.json()["config"]["name"] == "Plain"
