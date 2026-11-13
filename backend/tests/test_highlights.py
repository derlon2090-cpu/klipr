from app.worker.highlights import Word, build_filter_graph, write_ass
def test_ass_has_word_level_karaoke_for_arabic_and_english(tmp_path):
    destination = tmp_path / "captions.ass"; text = write_ass([Word(0, .2, "Hello"), Word(.2, .5, "العالم")], 0, 1, destination); contents = destination.read_text(encoding="utf-8")
    assert text == "Hello العالم" and "PlayResX: 1080" in contents and "\\kf20" in contents and "\\kf30" in contents and "العالم" in contents
def test_vertical_filter_graphs_are_9_by_16_and_split_when_facecam_found(tmp_path):
    ass = tmp_path / "captions.ass"; center = build_filter_graph(ass, "center"); split = build_filter_graph(ass, "split", (10, 20, 320, 180))
    assert "scale=1080:1920" in center and "crop=1080:1920" in center and "crop=320:180:10:20" in split and "scale=1080:960" in split and "vstack=inputs=2" in split
