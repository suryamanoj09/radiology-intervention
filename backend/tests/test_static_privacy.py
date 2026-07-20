"""Private-analysis-JSON guarantee: images/heatmaps are world-readable by id, but
the full analysis JSON lives in a NON-mounted dir and must never be served."""

from app import config


def test_uploaded_image_png_is_served(client, png_bytes):
    image_id = "aaaaaaaaaaaa"
    (config.UPLOADS_DIR / f"{image_id}.png").write_bytes(png_bytes)
    r = client.get(f"/static/uploads/{image_id}.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")


def test_analysis_json_is_not_served_from_uploads(client):
    image_id = "bbbbbbbbbbbb"
    # A JSON physically in the (private) analysis dir...
    (config.ANALYSIS_DIR / f"{image_id}.json").write_text('{"secret": true}', encoding="utf-8")
    # ...is not reachable through the uploads mount (no JSON exists there).
    r = client.get(f"/static/uploads/{image_id}.json")
    assert r.status_code == 404


def test_analysis_dir_has_no_static_mount(client):
    image_id = "cccccccccccc"
    (config.ANALYSIS_DIR / f"{image_id}.json").write_text("{}", encoding="utf-8")
    # There is deliberately no /static/analysis mount.
    r = client.get(f"/static/analysis/{image_id}.json")
    assert r.status_code == 404


def test_heatmap_png_is_served(client, png_bytes):
    image_id = "dddddddddddd"
    (config.HEATMAPS_DIR / f"{image_id}.png").write_bytes(png_bytes)
    r = client.get(f"/static/heatmaps/{image_id}.png")
    assert r.status_code == 200
