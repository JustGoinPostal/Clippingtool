from app.analytics import _raw_score, _extract_tiktok_post_id


def test_raw_score_rewards_views_and_engagement():
    weak,_ = _raw_score({"views":100,"likes":1,"comments":0,"shares":0,"saves":0})
    strong,_ = _raw_score({"views":10000,"likes":900,"comments":80,"shares":120,"saves":50})
    assert strong > weak
    assert 0 <= weak <= 100
    assert 0 <= strong <= 100


def test_retention_increases_confidence():
    _, no_ret = _raw_score({"views":5000,"likes":250})
    _, ret = _raw_score({"views":5000,"likes":250,"avg_view_percentage":82})
    assert ret > no_ret


def test_tiktok_public_id_from_status_json():
    row={"platform_post_id":"v_pub_file~v2.abc","result_json":"{\"publicaly_available_post_id\":[123456789]}"}
    assert _extract_tiktok_post_id(row)=="123456789"
