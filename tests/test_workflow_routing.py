"""Dispatching a probe must not start a five-hour render.

It did. The render job's condition was a deny-list - "run unless the task is
one of these" - and ``reel-entity-check`` was added without remembering to
exclude itself, so a sixty-clip calibration also launched a full long-form
render, which then took the ``video-generation`` concurrency group and held
it against the very measurement it had started beside.

The fix was an allow-list, and the reason it needs a test rather than a
comment is that the failure mode is *silent and additive*: nothing is wrong
with the workflow file until someone adds the ninth task, and by then the
cost is five runner-hours and a cancelled measurement. So this reads the
routing out of the YAML and asserts the property the allow-list has and the
deny-list did not - **every dispatchable task starts exactly one job** - for
whatever set of tasks exists at the time it runs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"

#: The task a job with no condition at all answers to. GitHub's own scheduled
#: and workflow_call paths pass no task, and the render is what they want.
DEFAULT_TASK = "render"


def load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # ``on:`` is YAML's boolean true. It has been that way since 1.1 and the
    # workflow file is not going to spell it differently.
    data["on"] = data.get("on") or data.get(True) or {}
    return data


def tasks_of(workflow: dict) -> list[str]:
    dispatch = workflow["on"].get("workflow_dispatch") or {}
    task = (dispatch.get("inputs") or {}).get("task") or {}
    return list(task.get("options") or [])


def fires_for(condition: str | None, task: str) -> bool:
    """Would this job's ``if:`` run for this task?

    A small evaluator rather than a regex over the whole expression: the
    conditions here are disjunctions of equality tests, which is exactly the
    shape an allow-list has, and anything more complicated should fail this
    test loudly rather than be guessed at.
    """

    if condition is None:
        return task == DEFAULT_TASK
    text = " ".join(str(condition).split())
    for clause in text.split("||"):
        clause = clause.strip()
        match = re.fullmatch(r"inputs\.task == (?:'([^']*)'|(null))", clause)
        assert match, f"not an allow-list clause: {clause!r}"
        wanted = match.group(1)
        if wanted is None:            # inputs.task == null
            wanted = ""
        if wanted == task or (wanted == "" and task == DEFAULT_TASK):
            return True
    return False


def test_every_dispatch_task_starts_exactly_one_job() -> None:
    workflow = load("generate-video.yml")
    tasks = tasks_of(workflow)
    assert tasks, "the video workflow has no task input"
    for task in tasks:
        started = [
            name for name, job in workflow["jobs"].items()
            if fires_for(job.get("if"), task)
        ]
        assert started == [task], f"dispatching {task!r} starts {started}"


def test_no_job_condition_is_a_deny_list() -> None:
    """The specific shape that caused it: ``!=`` anywhere in a job's ``if``.

    A deny-list is correct exactly until the next task is added, which is
    when nobody is looking at this file.
    """

    workflow = load("generate-video.yml")
    for name, job in workflow["jobs"].items():
        condition = str(job.get("if") or "")
        assert "!=" not in condition, (
            f"the {name} job excludes tasks instead of naming its own; "
            "that is what launched a five-hour render beside a calibration"
        )


def test_the_render_is_what_a_schedule_gets() -> None:
    """No task means the cron path, and the cron path means a video."""

    workflow = load("generate-video.yml")
    render = workflow["jobs"]["render"]
    assert fires_for(render.get("if"), "render")
    for task in tasks_of(workflow):
        if task != "render":
            assert not fires_for(render.get("if"), task), (
                f"the {task!r} probe would also start the long-form render"
            )


def test_the_probes_never_write_the_history() -> None:
    """Least privilege, and a second reason a stray render is expensive.

    The render commits ``data/state`` and needs ``contents: write``; a
    workflow-level permission is inherited by every job in the file, so a
    probe that says nothing about permissions is dispatchable with a write
    token it has no use for. Each one declares read.
    """

    workflow = load("generate-video.yml")
    assert workflow.get("permissions", {}).get("contents") == "write"
    for name, job in workflow["jobs"].items():
        if name == "render":
            continue
        assert (job.get("permissions") or {}).get("contents") == "read", (
            f"the {name} job inherits write access it does not need"
        )
