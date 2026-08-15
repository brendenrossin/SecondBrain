from secondbrain.feed.models import FeedItem
from secondbrain.feed.rank import (
    dedup_items,
    normalize_title,
    normalize_url,
    rank_items,
    recency_decay,
    score_item,
    select_top_n,
)

NOW = 1_700_000_000.0  # fixed reference epoch seconds


def _item(url, title, type="ai", trust=0.5, snippet="", published=None):
    return FeedItem(url=url, source_label="s", type=type, title=title,
                    snippet=snippet, published_at=published, trust=trust)


def test_normalize_url_strips_tracking_and_trailing_slash():
    assert normalize_url("https://x.com/a/?utm_source=rss&id=1") == "https://x.com/a?id=1"
    assert normalize_url("https://x.com/a/") == "https://x.com/a"


def test_normalize_title_lowercases_and_collapses_space():
    assert normalize_title("  Big   NEWS! ") == "big news!"


def test_dedup_by_url_and_title():
    items = [
        _item("https://x.com/a/", "Hello"),
        _item("https://x.com/a", "Hello"),        # same after normalize
        _item("https://x.com/b", "Hello"),         # same title, different url -> dup
        _item("https://x.com/c", "Different"),
    ]
    out = dedup_items(items)
    assert len(out) == 2


def test_recency_decay_favors_recent():
    recent = recency_decay(NOW - 3600, NOW)     # 1h old
    old = recency_decay(NOW - 3600 * 96, NOW)   # 96h old
    assert recent > old
    assert recency_decay(None, NOW) == 0.5      # unknown date -> neutral-ish


def test_score_rewards_interest_hits():
    interests = {"agents": 2.0}
    hit = _item("u1", "New agents framework", trust=1.0)
    miss = _item("u2", "Unrelated headline", trust=1.0)
    assert score_item(hit, interests, NOW) > score_item(miss, interests, NOW)


def test_rank_orders_descending():
    interests = {"agents": 2.0}
    items = [_item("u1", "boring", trust=0.5), _item("u2", "agents agents", trust=1.0)]
    ranked = rank_items(items, interests, now_ts=NOW)
    assert ranked[0].url == "u2"
    assert ranked[0].score >= ranked[1].score


def test_select_top_n_enforces_per_type_minimum():
    # 8 AI items outscore all sports; min_per_type must still pull sports in.
    ai = [_item(f"ai{i}", "agents", type="ai", trust=1.0) for i in range(8)]
    sports = [_item(f"sp{i}", "padres", type="sports", trust=0.2) for i in range(3)]
    interests = {"agents": 5.0, "padres": 0.1}
    ranked = rank_items(ai + sports, interests, now_ts=NOW)
    top = select_top_n(ranked, n=6, min_per_type=2, types=("ai", "sports"))
    assert len(top) == 6
    assert sum(1 for i in top if i.type == "sports") >= 2
