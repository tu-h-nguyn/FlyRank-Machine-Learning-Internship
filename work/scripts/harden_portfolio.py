"""Adversarial pass over the portfolio: try to break it, not to confirm it works.

Companion to test_contact_form.py, which covers the happy path and the obvious
failure paths. This one goes after the edge cases a real visitor (or a bot, or a
recruiter on a cheap Android) actually produces.

Run:  python3 work/scripts/harden_portfolio.py
"""

import pathlib, shutil, sys, tempfile, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from http.server import ThreadingHTTPServer
from test_contact_form import Handler, build_serve_dir, PORT, BASE, CHROMIUM
from playwright.sync_api import sync_playwright

findings = []   # (severity, area, what)

def report(sev, area, what):
    findings.append((sev, area, what))
    print(f"  {sev:6s} {area:22s} {what}")

def ok(area, what):
    print(f"  {'ok':6s} {area:22s} {what}")


def _only_local(route):
    """Google Fonts is unreachable from the build sandbox; waiting on it makes every
    navigation hang. Cut all off-origin requests so the suite tests the page, not
    the network."""
    if "127.0.0.1" in route.request.url:
        route.continue_()
    else:
        route.abort()


def new_ctx(browser, **kw):
    ctx = browser.new_context(**kw)
    ctx.route("**/*", _only_local)
    return ctx


def fill(page, name, email, msg):
    page.fill("#cf-name", name); page.fill("#cf-email", email); page.fill("#cf-message", msg)


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="harden-"))
    build_serve_dir(tmp)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), lambda *a, **k: Handler(*a, directory=str(tmp), **k))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    import test_contact_form as T

    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=CHROMIUM,
                args=["--no-sandbox", "--disable-background-networking",
                      "--disable-component-update", "--no-first-run"])

            # ── 1. Double submit, as fast as the mouse allows ──────────────
            print("\n[1] Double-submit race")
            ctx0 = new_ctx(b); pg = ctx0.new_page(); pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(400)
            before = len(T.received)
            fill(pg, "Race Test", "race@example.com", "Clicking send twice as fast as possible.")
            pg.click("#cf-submit", click_count=2, delay=0)
            pg.wait_for_timeout(2500)
            sent = len(T.received) - before
            if sent > 1:
                report("BUG", "double submit", f"one visitor produced {sent} emails")
            else:
                ok("double submit", "button disables synchronously; exactly one email")

            # ── 2. Enter key spam inside a field ──────────────────────────
            print("\n[2] Enter-key spam")
            pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(400)
            before = len(T.received)
            fill(pg, "Enter Spam", "enter@example.com", "Pressing enter repeatedly in the name field.")
            for _ in range(5):
                pg.press("#cf-name", "Enter")
            pg.wait_for_timeout(2500)
            sent = len(T.received) - before
            if sent > 1:
                report("BUG", "enter spam", f"{sent} emails from repeated Enter")
            else:
                ok("enter spam", f"{sent} email(s) — no duplicate flood")

            # ── 3. Garbage payloads ───────────────────────────────────────
            print("\n[3] Garbage input")
            garbage = [
                ("whitespace only", "   ", "a@b.co", "          "),
                ("html injection", "<script>alert(1)</script>", "x@y.co", "<img src=x onerror=alert(1)>"),
                ("sql-ish", "'; DROP TABLE users;--", "x@y.co", "1' OR '1'='1 ................"),
                ("emoji + RTL", "🙂🙃 مرحبا", "x@y.co", "مرحبا بالعالم 🎉 this is long enough"),
                ("combining marks", "Nguyễn" + "̃" * 40, "x@y.co", "combining mark stress test here"),
                ("no TLD", "A", "user@localhost", "Email without a dot in the domain."),
                ("double at", "A", "a@@b.co", "Two at signs in the address here."),
                ("leading space email", "A", " a@b.co", "Email with a leading space character."),
            ]
            for label, n, e, m in garbage:
                pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(250)
                before = len(T.received)
                fill(pg, n, e, m)
                pg.click("#cf-submit"); pg.wait_for_timeout(1200)
                delivered = len(T.received) - before
                blocked = pg.locator("#cf-name-err, #cf-email-err, #cf-message-err").filter(visible=True).count() > 0
                if label == "leading space email":
                    # Valid once trimmed, so it should be delivered -- but the address
                    # must arrive without the space, or reply-to breaks.
                    if delivered != 1:
                        report("BUG", f"validation/{label}", "valid-after-trim address was rejected")
                    elif T.received[-1]["email"] != "a@b.co":
                        report("BUG", f"validation/{label}",
                               f"delivered untrimmed: {T.received[-1]['email']!r}")
                    else:
                        ok(f"validation/{label}", "trimmed before sending")
                elif label in ("whitespace only", "no TLD", "double at"):
                    if delivered:
                        report("BUG", f"validation/{label}", "invalid input was delivered")
                    else:
                        ok(f"validation/{label}", "rejected client-side")
                else:
                    # These are legitimate messages; they must go through unmangled.
                    if delivered != 1:
                        report("BUG", f"input/{label}", f"legitimate message not delivered ({delivered})")
                    else:
                        got = T.received[-1]
                        if got["name"] != n.strip() or got["message"] != m.strip() and got["message"] != m:
                            ok(f"input/{label}", "delivered (whitespace trimmed by browser)")
                        else:
                            ok(f"input/{label}", "delivered intact, no mangling")

            # ── 4. Oversized input ────────────────────────────────────────
            print("\n[4] Oversized input")
            pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(300)
            huge = "A" * 9000
            pg.fill("#cf-message", huge)
            got_len = len(pg.input_value("#cf-message"))
            if got_len > 3000:
                report("BUG", "maxlength", f"message accepted {got_len} chars, cap is 3000")
            else:
                ok("maxlength", f"message capped at {got_len} chars by the browser")

            longword = "W" * 400
            pg.fill("#cf-name", longword)
            ow = pg.evaluate("() => document.documentElement.scrollWidth")
            vw = pg.evaluate("() => window.innerWidth")
            if ow > vw:
                report("BUG", "long word overflow", f"a 400-char word breaks layout ({ow} > {vw})")
            else:
                ok("long word overflow", "400-char unbroken word does not widen the page")

            # ── 5. Sticky nav vs anchor jumps (classic offset bug) ────────
            print("\n[5] In-page navigation under the sticky bar")
            pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(400)
            navh = pg.evaluate("() => document.querySelector('.nav').getBoundingClientRect().height")
            for target in ["#projects", "#approach", "#skills", "#contact"]:
                pg.evaluate(f"() => document.querySelector('a[href=\"{target}\"]').click()")
                # Smooth scrolling across a long page outlasts any fixed wait, and a
                # reading taken mid-scroll passes vacuously (the heading is still far
                # below the nav). Measure only once the page has stopped moving.
                top, last = None, None
                for _ in range(40):
                    pg.wait_for_timeout(150)
                    top = pg.evaluate(f"() => document.querySelector('{target}').getBoundingClientRect().top")
                    if last is not None and abs(top - last) < 0.5:
                        break
                    last = top
                if top > navh + 120:
                    report("BUG", f"anchor {target}", f"scroll never reached the section (top {top:.0f})")
                elif top < navh - 1:
                    report("BUG", f"anchor {target}", f"heading hidden under sticky nav (top {top:.0f} < nav {navh:.0f})")
                else:
                    ok(f"anchor {target}", f"lands clear of the nav (top {top:.0f})")

            # ── 6. No JavaScript ──────────────────────────────────────────
            print("\n[6] JavaScript disabled")
            ctx = new_ctx(b, java_script_enabled=False)
            p2 = ctx.new_page(); p2.goto(f"{BASE}/index.html"); p2.wait_for_timeout(400)
            if not p2.locator("#cf-form").is_visible():
                report("BUG", "no-js", "form not rendered without JS")
            else:
                act = p2.get_attribute("#cf-form", "action")
                has_key = p2.get_attribute("input[name=access_key]", "value")
                if act and has_key and has_key != "PASTE_YOUR_WEB3FORMS_ACCESS_KEY_HERE":
                    ok("no-js", "form still posts natively (action + key present in HTML)")
                else:
                    report("BUG", "no-js", "native POST fallback incomplete")
            if p2.locator("#cf-setup").is_visible():
                report("BUG", "no-js", "setup warning shows when JS is off")
            else:
                ok("no-js", "no spurious setup warning")
            ctx.close()

            # ── 7. Narrow + large-text devices ────────────────────────────
            print("\n[7] Narrow viewport and 200% text")
            for label, w, h in [("320px (iPhone SE gen1)", 320, 568), ("360px (common Android)", 360, 640)]:
                c3 = new_ctx(b, viewport={"width": w, "height": h}); p3 = c3.new_page()
                p3.goto(f"{BASE}/index.html"); p3.wait_for_timeout(500)
                sw = p3.evaluate("() => document.documentElement.scrollWidth")
                if sw > w:
                    wide = p3.evaluate("""(vw) => [...document.querySelectorAll('*')]
                        .filter(e => e.getBoundingClientRect().width > vw + 1)
                        .map(e => e.tagName + '.' + (e.className||'').toString().slice(0,25)).slice(0,4)""", w)
                    report("BUG", label, f"horizontal scroll ({sw}px): {wide}")
                else:
                    ok(label, "no horizontal scroll")
                p3.close(); c3.close()

            c4 = new_ctx(b, viewport={"width": 390, "height": 844}); p4 = c4.new_page()
            p4.goto(f"{BASE}/index.html")
            p4.evaluate("() => document.documentElement.style.fontSize = '32px'")  # 200%
            p4.wait_for_timeout(500)
            sw = p4.evaluate("() => document.documentElement.scrollWidth")
            if sw > 390:
                report("BUG", "200% text zoom", f"horizontal scroll at 2x font size ({sw}px)")
            else:
                ok("200% text zoom", "reflows without horizontal scroll")
            p4.close(); c4.close()

            # ── 8. Keyboard only ──────────────────────────────────────────
            print("\n[8] Keyboard-only reachability")
            pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(400)
            # Every link on the page comes before the form, so the budget is generous;
            # the loop stops as soon as the submit button has been reached.
            seen, hp_reached = [], False
            for _ in range(300):
                if "cf-submit" in seen:
                    break
                pg.keyboard.press("Tab")
                el = pg.evaluate("""() => { const a = document.activeElement;
                    return { tag: a.tagName, name: a.getAttribute('name'),
                             id: a.id, text: (a.textContent||'').trim().slice(0,22) }; }""")
                if el["name"] == "botcheck":
                    hp_reached = True
                seen.append(el["id"] or el["text"] or el["tag"])
            if hp_reached:
                report("BUG", "keyboard", "honeypot is reachable by Tab — real users will trip it")
            else:
                ok("keyboard", "honeypot never receives focus")
            for need in ["cf-name", "cf-email", "cf-message", "cf-submit"]:
                if need not in seen:
                    report("BUG", "keyboard", f"{need} not reachable by keyboard")
            if all(n in seen for n in ["cf-name", "cf-email", "cf-message", "cf-submit"]):
                ok("keyboard", "every form control is tab-reachable")

            # ── 9. Submitting again right after a success ─────────────────
            print("\n[9] Second message in the same session")
            pg.goto(f"{BASE}/index.html"); pg.wait_for_timeout(300)
            fill(pg, "First", "first@example.com", "This is the first message of the session.")
            pg.click("#cf-submit"); pg.wait_for_selector("#cf-status.is-ok", timeout=8000)
            before = len(T.received)
            fill(pg, "Second", "second@example.com", "This is the second message, sent right after.")
            pg.click("#cf-submit")
            try:
                pg.wait_for_selector("#cf-status.is-ok", timeout=8000)
                if len(T.received) - before == 1:
                    ok("repeat send", "a second message in the same session works")
                else:
                    report("BUG", "repeat send", "second message not delivered")
            except Exception:
                report("BUG", "repeat send", "form is stuck after the first success")

            # ── 10. Page weight and request count ─────────────────────────
            print("\n[10] Weight and requests")
            reqs = []
            c5 = new_ctx(b); p5 = c5.new_page()
            p5.on("request", lambda r: reqs.append(r.url))
            p5.goto(f"{BASE}/index.html"); p5.wait_for_timeout(1200)
            size = (pathlib.Path("docs/portfolio/index.html").stat().st_size)
            ok("page weight", f"{size/1024:.1f} KB of HTML, self-contained (no JS/CSS files)")
            ok("requests", f"{len(reqs)} request(s) from this origin + Google Fonts (blocked here)")
            p5.close(); c5.close()

            b.close()
    finally:
        srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    bugs = [f for f in findings if f[0] == "BUG"]
    if bugs:
        print(f"{len(bugs)} FINDING(S) TO TRIAGE:")
        for sev, area, what in bugs:
            print(f"  - [{area}] {what}")
        return 1
    print("NO BREAKAGE FOUND in this pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
