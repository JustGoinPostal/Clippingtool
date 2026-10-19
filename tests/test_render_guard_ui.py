from pathlib import Path

from app import paths


def test_runtime_dashboard_injects_render_guard_once(tmp_path: Path):
    static=tmp_path/"app"/"static"
    static.mkdir(parents=True)
    index=static/"index.html"
    index.write_text("<html><body><div>Postal AutoClip</div></body></html>",encoding="utf-8")

    paths._inject_runtime_dashboard_scripts(static)
    paths._inject_runtime_dashboard_scripts(static)

    html=index.read_text(encoding="utf-8")
    assert html.count('/static/render_guard.js')==1
    assert html.index('/static/render_guard.js') < html.index('</body>')


def test_render_guard_asset_is_bundled():
    asset=paths.RESOURCE_ROOT/"app"/"static"/"render_guard.js"
    text=asset.read_text(encoding="utf-8")
    assert "renderBusy" in text
    assert "waitForRender" in text
    assert "render-all" in text
