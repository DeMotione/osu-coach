from osu_coach.domain.exports.downloads import merge_collections, sets_to_download, unknown_sets


def test_merge_replaces_same_name_keeps_others_and_appends_new():
    existing = [("A", ["1"]), ("B", ["2"])]
    merged, replaced, added = merge_collections(existing, [("B", ["3"]), ("C", ["4"])])
    assert merged == [("A", ["1"]), ("B", ["3"]), ("C", ["4"])]
    assert replaced == ["B"] and added == ["C"]


def test_maps_without_a_known_set_are_looked_up_not_downloaded_as_set_0():
    rows = [("a", 10), ("b", 0), ("c", 10), ("d", -1), ("e", 0), ("b", 0)]
    assert sets_to_download(rows, {"c"}) == [10]
    assert unknown_sets(rows, {"e"}) == ["b", "d"]  # installed maps need no lookup
