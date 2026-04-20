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
from truck_bench.scoring.evaluator import score_numeric


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


def test_critic_yes_with_passing_signals_scores_both_dims() -> None:
    """Critic verdict is now ONE dimension, not a full override. When the
    agent both gets the critic's 'yes' AND the signals match, it scores
    2/2, not 1/1."""
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["driver", "CDL"])
    response = AgentResponse(scenario_id="Q1", agent_type="o",
                             answer="The driver holds a valid CDL")
    response.reasoning = f"__critic_verdict__=yes\n{response.answer}"
    r = score_response(response, golden)
    assert r.total_score == 2 and r.max_score == 2
    assert r.signals_correct is True
    assert "critic: yes" in r.notes


def test_critic_yes_with_missing_signals_splits_score() -> None:
    """Critic says yes but answer does not mention required tokens.
    Score 1/2: critic dimension passes, signal dimension fails."""
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["foo", "bar"])
    response = AgentResponse(scenario_id="Q1", agent_type="o",
                             answer="some text")
    response.reasoning = "__critic_verdict__=yes\nsome text"
    r = score_response(response, golden)
    assert r.total_score == 1 and r.max_score == 2
    assert r.signals_correct is False
    assert "critic: yes" in r.notes


def test_critic_no_with_passing_signals_splits_score() -> None:
    """Critic says no but answer happens to mention the lexical tokens.
    Score 1/2: critic dimension fails, signal dimension passes."""
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["driver"])
    response = AgentResponse(scenario_id="Q1", agent_type="n",
                             answer="driver")
    response.reasoning = "__critic_verdict__=no\ndriver"
    r = score_response(response, golden)
    assert r.total_score == 1 and r.max_score == 2
    assert "critic: no" in r.notes
    assert r.signals_correct is True


def test_signals_only_scenario_still_scores() -> None:
    """When no critic verdict is present, the signal dimension alone is
    scored (1/1 if matched)."""
    golden = GoldenAnswer(scenario_id="Q1", ontology_signals=["driver", "CDL"])
    response = AgentResponse(scenario_id="Q1", agent_type="o",
                             answer="The driver holds a valid CDL")
    r = score_response(response, golden)
    assert r.total_score == 1 and r.max_score == 1
    assert r.signals_correct is True


def test_score_numeric_percentage_within_tolerance() -> None:
    assert score_numeric("On-time delivery rate is 100%.", 100.0, 1.0) is True


def test_score_numeric_percentage_outside_tolerance() -> None:
    assert score_numeric("On-time delivery rate is 40%.", 100.0, 1.0) is False


def test_score_numeric_no_numbers_in_answer() -> None:
    assert score_numeric("The data is unavailable.", 100.0, 1.0) is False


def test_numeric_gold_adds_independent_dimension() -> None:
    golden = GoldenAnswer(
        scenario_id="Q13",
        gold_numeric_value=100.0,
        gold_numeric_tolerance_pct=1.0,
    )
    right = AgentResponse(scenario_id="Q13", agent_type="o",
                          answer="On-time delivery rate is 100%.")
    wrong = AgentResponse(scenario_id="Q13", agent_type="n",
                          answer="On-time delivery rate is 40%.")
    r_right = score_response(right, golden)
    r_wrong = score_response(wrong, golden)
    assert r_right.numeric_correct is True
    assert r_right.total_score == 1 and r_right.max_score == 1
    assert r_wrong.numeric_correct is False
    assert r_wrong.total_score == 0 and r_wrong.max_score == 1


def test_scorecard_rendering() -> None:
    naked = [ScoreResult("Q1", "naked", total_score=0, max_score=1, notes="critic: no")]
    onto = [ScoreResult("Q1", "ontology", total_score=1, max_score=1, notes="critic: yes",
                        signals_correct=True, metric_correct=True)]
    md = generate_scorecard(naked, onto)
    assert "# NakedAgent vs OntologyAgent" in md
    assert "| Q1 |" in md
    assert "Ontology" in md  # winner column
