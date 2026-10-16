"""Drive the whole app in a real browser against e2e/fake_stack.py and take screenshots.

    python -m uvicorn e2e.fake_stack:app --port 8700 &
    python e2e/run_browser_check.py [screenshot_dir]

Needs `pip install playwright` and a Chromium (set CHROMIUM_PATH if it isn't on Playwright's default path).
"""

import io
import os
import sys
from pathlib import Path

from docx import Document
from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:8700"
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e/screenshots")
SHOTS.mkdir(parents=True, exist_ok=True)


def docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buf)
    return buf.getvalue()


def step(message: str) -> None:
    print(f"  ok  {message}")


with sync_playwright() as p:
    launch = {"args": ["--no-sandbox"]}
    if os.environ.get("CHROMIUM_PATH"):
        launch["executable_path"] = os.environ["CHROMIUM_PATH"]
    browser = p.chromium.launch(**launch)
    ctx = browser.new_context(viewport={"width": 1180, "height": 780})
    page = ctx.new_page()
    problems = []
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)

    # 1. sign in -------------------------------------------------------------------------------------------
    page.goto(BASE)
    expect(page.get_by_role("heading", name="Compass")).to_be_visible()
    page.screenshot(path=SHOTS / "01-login.png")
    page.get_by_label("Email address").fill("aun@example.com")
    page.get_by_role("button", name="Email me a code").click()
    expect(page.get_by_text("We sent a code to")).to_be_visible()
    page.get_by_label("Code from the email").fill("123456")
    page.get_by_role("button", name="Sign in").click()
    step("signed in with the emailed code (real JWT, verified through JWKS)")

    # 2. consent gate ------------------------------------------------------------------------------------------
    expect(page.get_by_role("heading", name="Welcome to Compass")).to_be_visible()
    page.screenshot(path=SHOTS / "02-consent.png", full_page=True)
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("alert")).to_contain_text("tick the first box")
    page.get_by_label("I understand how Compass uses my information").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Hi, I'm Compass, an AI career coach.")).to_be_visible()
    step("consent required, then accepted; app loaded afterwards")
    page.screenshot(path=SHOTS / "03-chat-empty.png")

    # 3. chat streaming -----------------------------------------------------------------------------------------
    page.get_by_label("Message Compass").fill("My manager says I need to be more strategic.")
    page.keyboard.press("Enter")
    expect(page.get_by_text("Thanks for sharing that")).to_be_visible()
    page.screenshot(path=SHOTS / "04-chat-streaming.png")
    expect(page.get_by_role("button", name="Good reply")).to_be_visible(timeout=15000)  # appears once saved
    expect(page).to_have_url(f"{BASE}/c/c1")
    expect(page.get_by_text("Next steps this week:")).to_be_visible()  # the stream survived the URL change
    expect(page.locator(".bubble strong").first).to_be_visible()  # markdown rendered
    page.get_by_role("button", name="Good reply").click()
    expect(page.get_by_role("button", name="Good reply")).to_have_attribute("aria-pressed", "true")
    page.screenshot(path=SHOTS / "05-chat-reply.png")
    step("reply streamed, markdown rendered, URL moved to /c/c1 without losing the stream, thumbs saved")
    expect(page.locator(".history a").first).to_contain_text("My manager says")
    step("conversation appears in the sidebar history")

    # 4. other pages ----------------------------------------------------------------------------------------------
    page.get_by_role("link", name="Profile").click()
    page.get_by_label("Current role").fill("Senior analyst")
    page.get_by_label("Career goals").fill("Move into management within 12 months")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved.")).to_be_visible()
    page.screenshot(path=SHOTS / "06-profile.png")

    page.get_by_role("link", name="Documents").click()
    expect(page.get_by_text("performance-review-2025.docx")).to_be_visible()
    page.set_input_files("input[type=file]", [
        {"name": "job-description.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "buffer": docx_bytes("Senior analyst. Lead a team of three. Stakeholder reporting.")},
        {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"Goal: ask for feedback every month."},
        {"name": "empty.txt", "mimeType": "text/plain", "buffer": b"   "},
    ])
    expect(page.get_by_text("Added job-description.docx")).to_be_visible()
    expect(page.get_by_text("empty.txt: I couldn't find any text")).to_be_visible()
    expect(page.get_by_text("Context in use:")).to_be_visible()
    page.screenshot(path=SHOTS / "07-documents.png", full_page=True)
    page.get_by_role("switch", name="Use notes.txt in conversations").click()
    expect(page.get_by_role("switch", name="Use notes.txt in conversations")).to_have_attribute("aria-checked", "false")
    page.get_by_role("button", name="Remove notes.txt").click()
    expect(page.locator(".doc-name", has_text="notes.txt")).to_have_count(0)
    step("profile saved; documents uploaded, bad file reported, toggled off, removed")

    page.get_by_role("link", name="Privacy").click()
    page.get_by_role("switch", name="Allow my chats to be used for improving Compass").click()
    expect(page.get_by_role("switch", name="Allow my chats to be used for improving Compass")).to_have_attribute("aria-checked", "true")
    page.screenshot(path=SHOTS / "08-privacy.png")
    step("training opt-in toggled")

    # 5. staying signed in + reopening history -------------------------------------------------------------------------
    page.reload()
    expect(page.get_by_role("link", name="Privacy")).to_be_visible()  # no login screen: the session persisted
    page.locator(".history a").first.click()
    expect(page.get_by_text("Next steps this week:")).to_be_visible()
    expect(page.get_by_role("button", name="Good reply")).to_have_attribute("aria-pressed", "true")  # rating remembered
    page.get_by_label("Message Compass").fill("Can you give me an example question to ask?")
    page.keyboard.press("Enter")
    expect(page.get_by_role("button", name="Good reply")).to_have_count(2, timeout=15000)
    page.screenshot(path=SHOTS / "09-history-continue.png")
    step("reload keeps the user signed in; past conversation reopens with its rating and can be continued")

    # 6. end session ----------------------------------------------------------------------------------------------------
    page.get_by_role("button", name="End session").click()
    expect(page.get_by_text("Saved a note so Compass remembers this next time.")).to_be_visible()
    step("end session saves a memory note")

    # 7. phone layout ----------------------------------------------------------------------------------------------------
    phone = browser.new_context(viewport={"width": 390, "height": 780}, storage_state=ctx.storage_state())
    m = phone.new_page()
    m.goto(BASE)
    m.locator(".history a").first.wait_for()
    m.screenshot(path=SHOTS / "10-phone-chat.png")
    m.get_by_role("button", name="Open menu").click()
    expect(m.get_by_role("link", name="Documents")).to_be_visible()
    m.wait_for_timeout(500)  # let the drawer finish sliding in
    assert m.get_by_role("link", name="Documents").bounding_box()["x"] >= 0, "drawer is still off-screen"
    m.screenshot(path=SHOTS / "11-phone-menu.png")
    m.get_by_role("link", name="Documents").click()
    expect(m.get_by_role("heading", name="Your documents")).to_be_visible()
    m.screenshot(path=SHOTS / "12-phone-documents.png", full_page=True)
    step("phone layout: drawer menu and pages work")

    # 8. delete my data -----------------------------------------------------------------------------------------------------
    page.get_by_role("link", name="Privacy").click()
    page.get_by_role("button", name="Delete everything").click()
    expect(page.get_by_role("alert")).to_contain_text("Type DELETE")
    page.get_by_label("Type DELETE to confirm").fill("DELETE")
    page.get_by_role("button", name="Delete everything").click()
    expect(page.get_by_text("Your conversations, documents and profile have been deleted.")).to_be_visible()
    expect(page.get_by_label("Email address")).to_be_visible()
    page.screenshot(path=SHOTS / "13-after-delete.png")
    step("delete my data wipes everything and returns to sign-in with a confirmation")

    browser.close()
    if problems:
        print("\nBROWSER PROBLEMS:")
        print("\n".join(problems))
        sys.exit(1)
    print("\nAll browser checks passed.")
