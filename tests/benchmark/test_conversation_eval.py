"""Check that the evaluator itself detects misleading outputs."""
from scripts.evaluate_conversations import objective_checks


def test_evaluator_rejects_unknown_required_attribute(recommendation_factory):
    rec = recommendation_factory().model_dump(mode="json")
    rec["distance_m"] = 0
    rec["caveats"] = ["Путь не проверен."]
    case = {"required_attributes":["sockets"],"max_effective_minutes":60}
    body = {"recommendations":[rec],"trace":{}}
    failures = objective_checks(case,body,{"latitude":51.09,"longitude":71.41},{"test:1"})
    assert "test:1:unconfirmed_sockets" in failures


def test_evaluator_rejects_invented_id_and_travel_time(recommendation_factory):
    rec = recommendation_factory().model_dump(mode="json")
    rec["walking_minutes"] = 10
    body = {"recommendations":[rec],"trace":{}}
    failures = objective_checks({"max_effective_minutes":60},body,
                                {"latitude":51.09,"longitude":71.41},set())
    assert "test:1:unknown_poi" in failures
    assert "test:1:unverified_travel_time" in failures


def test_evaluator_does_not_count_empty_unsafe_reply_as_success():
    failures = objective_checks({"max_effective_minutes":60,"expect_clarification":True,"expect_empty":True},
                                {"recommendations":[],"trace":{}},
                                {"latitude":51.09,"longitude":71.41},set())
    assert failures == ["missing_clarification"]
