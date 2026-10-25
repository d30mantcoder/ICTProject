"""Measure the Assignment 4 image change on the local prototype with test API data."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1] / "bridge-test"
OUT = Path(__file__).resolve().parent


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def measure(browser, origin, variant):
    context = browser.new_context(viewport={"width": 360, "height": 800}, device_scale_factor=1)
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    requests = {}
    start = [None]

    def on_request(event):
        if not event["request"]["url"].startswith(origin):
            return
        if start[0] is None:
            start[0] = event["timestamp"]
        requests[event["requestId"]] = {
            "path": urlparse(event["request"]["url"]).path,
            "bytes": 0,
            "finished_at": None,
        }

    def on_finish(event):
        if event["requestId"] in requests:
            requests[event["requestId"]]["bytes"] = event["encodedDataLength"]
            requests[event["requestId"]]["finished_at"] = event["timestamp"]

    cdp.on("Network.requestWillBeSent", on_request)
    cdp.on("Network.loadingFinished", on_finish)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    # Chrome DevTools Fast 4G preset: 150 ms latency, 1.6 Mbps down, 750 Kbps up.
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False,
        "latency": 150,
        "downloadThroughput": 1_600_000 / 8,
        "uploadThroughput": 750_000 / 8,
    })

    def index_route(route):
        html = (ROOT / "index.html").read_text()
        if variant == "before":
            html = html.replace('src="/attendance-preview.webp"', 'src="/attendance-preview.png"')
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)

    def api_route(route):
        path = urlparse(route.request.url).path
        if path == "/api/connect":
            route.fulfill(json={"ok": True})
        elif path == "/api/resume":
            route.fulfill(json={"message": "Тестовый вход"})
        elif path == "/api/state":
            route.fulfill(status=401, json={"active": False})
        else:
            route.fulfill(json={"phase": "idle", "message": "Готово"})

    page.route(origin + "/", index_route)
    page.route(origin + "/api/**", api_route)
    # External font transfer is excluded so the local image comparison is repeatable.
    page.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(content_type="text/css", body=""))
    page.goto(origin + "/", wait_until="load", timeout=30_000)
    page.locator("#signIn").wait_for(state="visible")
    page.locator(".preview-figure img").evaluate("img => img.decode()")
    page.wait_for_timeout(700)
    if variant == "after":
        page.screenshot(path=str(OUT / "part-b-mobile-360.png"), full_page=True)
    rows = list(requests.values())
    completed = [r["finished_at"] for r in rows if r["finished_at"] is not None]
    image_name = "attendance-preview.png" if variant == "before" else "attendance-preview.webp"
    image_rows = [r for r in rows if r["path"] == "/" + image_name]
    if len(image_rows) != 1 or image_rows[0]["bytes"] < (ROOT / image_name).stat().st_size:
        raise RuntimeError("Chromium did not report the image transfer; use DevTools Network measurements")
    result = {
        "variant": variant,
        "image": "/" + image_name,
        "viewport_width_px": 360,
        "throttle": "Fast 4G: 150 ms RTT; 1.6 Mbps down; 750 Kbps up",
        "cache_disabled": True,
        "local_transfer_bytes": sum(r["bytes"] for r in rows),
        "local_requests": len(rows),
        "local_finish_ms": round((max(completed) - start[0]) * 1000) if completed else None,
        "requests": sorted(rows, key=lambda r: r["path"]),
    }
    context.close()
    return result


def main():
    handler = partial(QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            before = measure(browser, origin, "before")
            after = measure(browser, origin, "after")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    output = {"method": "Chromium CDP encodedDataLength; local resources only; test API responses", "before": before, "after": after}
    (OUT / "part-b-network.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: {x: v[x] for x in ("local_transfer_bytes", "local_requests", "local_finish_ms")} for k, v in (("before", before), ("after", after))}, indent=2))


if __name__ == "__main__":
    main()
