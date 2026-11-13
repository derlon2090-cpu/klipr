from app.worker.outro import SAFE_ZONES, concat_command, recommendation_slots, render_outro
def test_safe_zones_and_fallbacks(tmp_path):
    assert SAFE_ZONES == ((110,310,560,315),(1250,310,560,315))
    assert recommendation_slots([]) == [None,None] and recommendation_slots(["one"])[1] is None and recommendation_slots(["one","two"])[1] == "two"
    output = tmp_path / "outro.mp4"; command = concat_command(tmp_path/"vod.mp4", output, tmp_path/"final.mp4")
    assert command[0] == "ffmpeg" and "concat=n=2" in command[7]
