from osu_coach.exports.domain import merge_collections


def test_merge_replaces_same_name_keeps_others_and_appends_new():
    existing = [("A", ["1"]), ("B", ["2"])]
    merged, replaced, added = merge_collections(existing, [("B", ["3"]), ("C", ["4"])])
    assert merged == [("A", ["1"]), ("B", ["3"]), ("C", ["4"])]
    assert replaced == ["B"] and added == ["C"]
