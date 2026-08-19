"""Browser controller built on Playwright.

Produces a text-only, numbered-element view of a page — mirroring dsh-browser's
design so the model operates the page without screenshots. Sensitive fields
(passwords, payment card inputs) are always masked.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings


@dataclass
class Element:
    index: int
    tag: str
    role: str
    text: str
    selector: str


# JS that walks the DOM and returns interactive elements in a stable order.
#
# Each snapshot is stamped with a monotonic `gen` (generation) token. We first
# clear every stamp from the previous generation, then tag the currently-visible
# controls with (idx, gen). Locators match on BOTH idx and gen, so an index taken
# from an older snapshot resolves to zero elements after the page mutates —
# turning the classic "stale index" failure into a clean re-snapshot prompt
# instead of a strict-mode "resolved to 2 elements" crash or a silent mis-click.
#
# Element identity is kept STABLE across snapshots via a signature
# (`tag|role|text#occurrence`): a control that persists keeps the same index it
# had before (looked up in `prevMap`), and only genuinely new controls consume a
# fresh index from the `next` counter. That stability is what makes `delta` mode
# meaningful — "changed elements" would be noise if every snapshot re-numbered
# everything — while still keeping unchanged controls clickable by their old
# number under the current generation.
_COLLECT_JS = r"""
([gen, prevMap, startNext]) => {
  document.querySelectorAll('[data-agent-idx]').forEach((el) => {
    el.removeAttribute('data-agent-idx');
    el.removeAttribute('data-agent-gen');
  });
  const SELECTOR = 'a, button, input, textarea, select, [role=button], [onclick]';
  const nodes = Array.from(document.querySelectorAll(SELECTOR));
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const sensitive = (el) => {
    const t = (el.getAttribute('type') || '').toLowerCase();
    const name = (el.getAttribute('name') || '').toLowerCase();
    const auto = (el.getAttribute('autocomplete') || '').toLowerCase();
    return t === 'password' || /card|cvc|cvv|ccnum/.test(name) || /cc-number|cc-csc/.test(auto);
  };
  const counts = {};
  const usedIdx = new Set();
  let next = startNext;
  const out = [];
  for (const el of nodes.filter(visible)) {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || el.getAttribute('type') || tag;
    let label = (el.innerText || el.value || el.getAttribute('aria-label') ||
                 el.getAttribute('placeholder') || el.getAttribute('name') || '').trim();
    if (sensitive(el)) label = '••••';
    const text = label.slice(0, 120);
    const base = tag + '|' + role + '|' + text;
    const c = counts[base] = (counts[base] || 0) + 1;
    const sig = base + '#' + c;
    let idx, isNew;
    if (Object.prototype.hasOwnProperty.call(prevMap, sig) && !usedIdx.has(prevMap[sig])) {
      idx = prevMap[sig];
      isNew = false;
    } else {
      idx = next++;
      isNew = true;
    }
    usedIdx.add(idx);
    el.setAttribute('data-agent-idx', String(idx));
    el.setAttribute('data-agent-gen', String(gen));
    out.push({ index: idx, tag, role, text, sig, isNew });
  }
  const sigmap = {};
  for (const e of out) sigmap[e.sig] = e.index;
  return { elements: out, next, sigmap };
}
"""


class BrowserController:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        # Monotonic snapshot generation. Bumped on every snapshot so element
        # indices from a stale snapshot can't resolve after the DOM changes.
        self._gen = 0
        self._last_elements: list[dict] = []
        # Stable-identity bookkeeping for delta snapshots.
        self._prev_sigmap: dict[str, int] = {}
        self._next_index = 0

    def start(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        if settings.user_data_dir:
            # Reuse a real browser profile: sessions/cookies persist across runs.
            # launch_persistent_context returns a BrowserContext (no separate
            # Browser handle); it reopens the profile's existing pages.
            launch_kwargs: dict = {
                "user_data_dir": settings.user_data_dir,
                "headless": settings.headless,
            }
            if settings.browser_channel:
                launch_kwargs["channel"] = settings.browser_channel
            self._context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
            self._page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
        else:
            launch_kwargs = {"headless": settings.headless}
            if settings.browser_channel:
                launch_kwargs["channel"] = settings.browser_channel
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()

    def stop(self):
        # Persistent contexts have no Browser handle — close the context itself.
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # --- tool primitives -------------------------------------------------
    def navigate(self, url: str) -> str:
        self._page.goto(url, wait_until="domcontentloaded")
        # New document => nothing carries over; restart identity tracking so
        # coincidental label matches across pages aren't treated as "unchanged".
        self._prev_sigmap = {}
        self._next_index = 0
        return f"Navigated to {self._page.url}"

    def wait(
        self,
        until: str = "settle",
        selector: str | None = None,
        timeout_ms: int | None = None,
    ) -> str:
        """Block until the page load/render settles (or a selector appears).

        until: "settle"/"networkidle" waits for network to go idle (best effort —
        pages with long-lived connections never fully idle, so a timeout here is
        treated as "settled enough" rather than an error); "load" waits for the
        load event; "domcontentloaded" for the DOM.
        """
        from playwright.sync_api import TimeoutError as PWTimeout

        timeout = timeout_ms or settings.wait_timeout_ms
        notes: list[str] = []
        if selector:
            try:
                self._page.wait_for_selector(selector, timeout=timeout, state="visible")
                notes.append(f"selector '{selector}' is visible")
            except PWTimeout:
                return f"Timed out after {timeout}ms waiting for selector '{selector}'"
        state = {
            "settle": "networkidle",
            "networkidle": "networkidle",
            "load": "load",
            "domcontentloaded": "domcontentloaded",
        }.get(until, "networkidle")
        try:
            self._page.wait_for_load_state(state, timeout=timeout)
            notes.append(f"reached load state '{state}'")
        except PWTimeout:
            notes.append(
                f"load state '{state}' not reached within {timeout}ms; continuing"
            )
        return "Wait complete: " + "; ".join(notes)

    def snapshot(self, delta: bool = False) -> str:
        self._gen += 1
        title = self._page.title()
        url = self._page.url
        result = self._page.evaluate(
            _COLLECT_JS, [self._gen, self._prev_sigmap, self._next_index]
        )
        elements = result["elements"]
        self._next_index = result["next"]
        new_sigmap = result["sigmap"]

        prev_sigs = set(self._prev_sigmap.keys())
        cur_sigs = set(new_sigmap.keys())
        added = [e for e in elements if e["sig"] not in prev_sigs]
        removed = sorted(prev_sigs - cur_sigs)

        self._prev_sigmap = new_sigmap
        self._last_elements = elements

        if delta and prev_sigs:
            lines = [
                f"TITLE: {title}",
                f"URL: {url}",
                "",
                "CHANGES SINCE LAST SNAPSHOT:",
            ]
            if not added and not removed:
                lines.append("  (no interactive controls changed)")
            for e in added:
                lines.append(
                    f"  + [{e['index']}] <{e['tag']}/{e['role']}> {e['text']}"
                )
            for sig in removed:
                # sig == "tag|role|text#occurrence"; surface the human label.
                label = sig.rsplit("#", 1)[0].split("|", 2)[-1]
                lines.append(f"  - removed: {label!r}")
            unchanged = len(elements) - len(added)
            lines.append(
                f"  ({unchanged} unchanged control(s) retained with their numbers)"
            )
            return "\n".join(lines)

        body = self._page.inner_text("body")[:4000]
        lines = [f"TITLE: {title}", f"URL: {url}", "", "PAGE TEXT:", body, "", "CONTROLS:"]
        for e in elements:
            lines.append(f"  [{e['index']}] <{e['tag']}/{e['role']}> {e['text']}")
        return "\n".join(lines)

    def _locator(self, index: int):
        # Match idx AND the current generation so a stale index (from a snapshot
        # taken before the DOM changed) resolves to nothing rather than the wrong
        # element or a duplicate.
        return self._page.locator(
            f"[data-agent-idx='{index}'][data-agent-gen='{self._gen}']"
        )

    _STALE_MSG = (
        "Element [{index}] is not available in the current page state — either it "
        "does not exist or the page changed since the last snapshot. Call "
        "browser_snapshot to get fresh element numbers, then retry."
    )

    def click(self, index: int) -> str:
        loc = self._locator(index)
        if loc.count() == 0:
            return self._STALE_MSG.format(index=index)
        loc.click(timeout=5000)
        return f"Clicked element [{index}]"

    def type_text(self, index: int, text: str, replace: bool = False) -> str:
        loc = self._locator(index)
        if loc.count() == 0:
            return self._STALE_MSG.format(index=index)
        if replace:
            loc.fill(text)
        else:
            loc.click()
            loc.type(text)
        return f"Typed into element [{index}]"

    def press(self, key: str) -> str:
        self._page.keyboard.press(key)
        return f"Pressed {key}"

    def scroll(self, direction: str) -> str:
        amounts = {"down": 800, "up": -800, "top": "top", "bottom": "bottom"}
        if direction in ("top", "bottom"):
            self._page.evaluate(
                f"window.scrollTo(0, {'0' if direction == 'top' else 'document.body.scrollHeight'})"
            )
        else:
            self._page.mouse.wheel(0, amounts.get(direction, 800))
        return f"Scrolled {direction}"

    def get_text(self, selector: str) -> str:
        try:
            return self._page.inner_text(selector)[:4000]
        except Exception as e:  # noqa: BLE001
            return f"Could not read '{selector}': {e}"

    def current_url(self) -> str:
        return self._page.url

    def label_for(self, index: int) -> str:
        """Human label of a control from the most recent snapshot (for risk
        checks/confirmation prompts). Empty if unknown."""
        for e in self._last_elements:
            if e.get("index") == index:
                return e.get("text", "")
        return ""
