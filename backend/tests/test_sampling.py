from reelhaven.sampling import Candidate, choose_samples


def c(
    file_id: int, size: int, title: int | None = 1, height: int = 1080, hdr: str = "sdr"
) -> Candidate:
    return Candidate(file_id, size, title, height, hdr)


def test_one_sample_is_the_largest_file() -> None:
    files = [c(1, 10), c(2, 30, height=2160, hdr="hdr10"), c(3, 20)]
    assert choose_samples(files, 1) == [2]


def test_nothing_to_choose() -> None:
    assert choose_samples([], 3) == []
    assert choose_samples([c(1, 10)], 5) == [1]


def test_prefers_each_kind_of_video_first() -> None:
    files = [
        c(1, 100, title=1),
        c(2, 90, title=2),
        c(3, 50, title=3, height=2160, hdr="hdr10"),
        c(4, 40, title=4, height=720),
        c(5, 30, title=5, height=2160),  # 4K SDR is its own kind
    ]
    assert choose_samples(files, 4) == [1, 3, 4, 5]


def test_resolution_buckets_tolerate_cropped_video() -> None:
    files = [c(1, 100, title=1, height=1080), c(2, 90, title=2, height=804), c(3, 80, title=3)]
    # 1920x804 (scope) is 1080p too, so the second pick is just the next title.
    assert choose_samples(files, 2) == [1, 2]


def test_then_spreads_over_titles() -> None:
    episodes = [c(i, 100 - i, title=1) for i in range(1, 5)]
    other_show = [c(10, 50, title=2)]
    assert choose_samples(episodes + other_show, 2) == [1, 10]


def test_then_fills_with_the_largest() -> None:
    episodes = [c(i, 100 - i, title=1) for i in range(1, 5)]
    assert choose_samples(episodes, 3) == [1, 2, 3]


def test_files_without_a_title_count_as_separate() -> None:
    files = [c(1, 100, title=None), c(2, 90, title=None), c(3, 80, title=1), c(4, 70, title=1)]
    assert choose_samples(files, 3) == [1, 2, 3]


def test_ties_are_stable() -> None:
    files = [c(2, 10, title=1), c(1, 10, title=1)]
    assert choose_samples(files, 1) == [1]
