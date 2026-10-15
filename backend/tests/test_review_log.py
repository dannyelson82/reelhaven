from reelhaven.review import ReviewItem
from reelhaven.review_log import reconcile


def item(file_id: int, kind: str = "failed") -> ReviewItem:
    return ReviewItem(
        kind=kind,  # type: ignore[arg-type]
        file_id=file_id,
        library_id=1,
        library_name="Movies",
        relative_path=f"{file_id}.mkv",
        size=1,
        detail="why",
        ignored=False,
    )


def test_reconcile_adds_refreshes_and_resolves() -> None:
    still, gone = item(1), item(2)
    other_kind = item(1, "no_gain")
    changes = reconcile({(1, "failed"): 10, (2, "failed"): 11}, [still, other_kind, item(3)])
    assert changes.seen == {10: still}
    assert changes.resolved == [11]
    assert [(i.file_id, i.kind) for i in changes.new] == [(1, "no_gain"), (3, "failed")]
    assert gone not in changes.new


def test_reconcile_with_nothing_open() -> None:
    changes = reconcile({}, [])
    assert (changes.new, changes.seen, changes.resolved) == ([], {}, [])
