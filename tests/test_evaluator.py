"""Unit tests for the scorer."""

from __future__ import annotations

from truck_bench.scoring import (
    AgentResponse,
    GoldenAnswer,
    ScoreResult,
    generate_scorecard,
    normalize_text,
    score_response,
    score_signals,
)


def test_normalize_text_folds_separators() -> None:
    assert normalize_text("write_off_flag") == "write off flag"
    assert normalize_text("write-off  flag") == "write off flag"
    assert normalize_text("a/b-c_d") == "a b c d"


def test_score_signals_all_match() -> None:
    ok, matched, missing = score_signals(
        "The BORROWER has annual_income > 100000",
        ["borrower", "annual_income"],
    )
    assert ok is True
    assert set(matched) == {"borrower", "annual_income"}
    assert missing == []


def test_score_signals_separator_normalization() -> None:
    ok, matched, missing = score_signals(
        "There are 15 loans with the write-off flag set to TRUE.",
        ["write_off_flag", "loan"],
    )
    assert ok is True
    assert set(matched) == {"write_off_flag", "loan"}


def test_score_signals_missing_flagged() -> None:
    ok, matched, missing = score_signals("only driver", ["driver", "CDL"])
    assert ok is False
    assert matched == ["driver"]
    assert missing == ["CDL"]


def test_critic_verdict_yes_wins() -> None:
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["foo", "bar"])
    response = AgentResponse(scenario_id="Q1", agent_type="o")
    response.reasoning = "__critic_verdict__=yes\nsome text"
    r = score_response(response, golden)
    assert r.total_score == 1 and r.max_score == 1
    assert r.signals_correct is True
    assert "critic: yes" in r.notes


def test_critic_verdict_no_scores_zero() -> None:
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["foo"])
    response = AgentResponse(scenario_id="Q1", agent_type="n")
    response.reasoning = "__critic_verdict__=no\nsome text"
    r = score_response(response, golden)
    assert r.total_score == 0 and r.max_score == 1
    assert "critic: no" in r.notes


def test_fallback_to_signal_match_when_no_verdict() -> None:
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["driver", "CDL"])
    response = AgentResponse(
        scenario_id="Q1",
        agent_type="o",
        answer="The driver holds a valid CDL",
    )
    # No verdict marker in reasoning -> fallback to token match
    r = score_response(response, golden)
    assert r.total_score == 1 and r.max_score == 1
    assert r.signals_correct is True


def test_scorecard_rendering() -> None:
    naked = [ScoreResult("Q1", "naked", total_score=0, max_score=1, notes="critic: no")]
    onto = [ScoreResult("Q1", "ontology", total_score=1, max_score=1, notes="critic: yes",
                        signals_correct=True, metric_correct=True)]
    md = generate_scorecard(naked, onto)
    assert "# NakedAgent vs OntologyAgent" in md
    assert "| Q1 |" in md
    assert "Ontology" in md  # winner column
