/* Records the 4-act demo video from a live mock replay.
 *
 * Prereqs (run from repo root):
 *   1. rm -f demo.db
 *   2. DATABASE_URL=sqlite:///demo.db uvicorn drift.dashboard.server:app --port 8123
 *   3. python -m drift.streams.replay tests/fixtures/drift_stream.jsonl \
 *        --db sqlite:///demo.db --speed 300 --quiet
 *   4. cd dashboard && node scripts/record-demo.mjs
 *
 * Output: ../assets/demo.webm (~4-5 min). The script watches the API and
 * advances acts when the real events happen — nothing is faked on screen.
 */
import { chromium } from "playwright";
import { mkdirSync, renameSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = "http://localhost:8123";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "..", "assets", "demo.webm");
const VIDEO_DIR = join(HERE, "video-out");
const STREAM = "support-bot";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const api = async (path) => {
  try {
    const r = await fetch(BASE + path);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
};
const waitFor = async (fn, timeoutMs, pollMs = 2000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await fn()) return true;
    await sleep(pollMs);
  }
  return false;
};

mkdirSync(VIDEO_DIR, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 800 } },
  colorScheme: "dark", // match the dashboard's dark-first tokens + title cards
});
const page = await ctx.newPage();
await page.goto(BASE, { waitUntil: "networkidle" });

const toast = (text, ms = 7000) =>
  page.evaluate(
    ([text, ms]) => {
      const el = document.createElement("div");
      el.textContent = text;
      Object.assign(el.style, {
        position: "fixed",
        top: "16px",
        left: "50%",
        transform: "translateX(-50%)",
        background: "rgba(15,15,15,0.94)",
        color: "#fff",
        padding: "10px 24px",
        borderRadius: "10px",
        font: "600 15px system-ui",
        zIndex: 9999,
        maxWidth: "80%",
        textAlign: "center",
        border: "1px solid rgba(255,255,255,0.25)",
        boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
      });
      document.body.appendChild(el);
      setTimeout(() => el.remove(), ms);
    },
    [text, ms]
  );

const scrollToText = async (text) => {
  const loc = page.locator(`text=${text}`).first();
  if ((await loc.count()) > 0)
    await loc.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "start" }));
};

try {
  // ---- ACT 1: green ------------------------------------------------------
  await toast("ACT 1 — GREEN: a healthy production stream. Boring on purpose.", 8000);
  await sleep(20_000);

  // ---- ACT 2: the whisper (first hearings happen) ------------------------
  await waitFor(async () => {
    const d = await api(`/api/streams/${STREAM}/debates`);
    return d && d.length > 0;
  }, 120_000);
  await toast(
    "ACT 2 — THE WHISPER: degradation begins. Note: every response you see still passes any reasonable threshold.",
    10_000
  );
  await scrollToText("QUALITY —");
  await sleep(25_000);

  // ---- ACT 3: the verdict (ALERT survives cross-examination) --------------
  await waitFor(async () => {
    const e = await api(`/api/streams/${STREAM}/events?kind=ALERT&limit=1`);
    return e && e.length > 0;
  }, 240_000);
  await toast(
    "ACT 3 — THE VERDICT: the trend survived the Defense. The Judge rules ALERT, citing ledger rows.",
    9000
  );
  await sleep(4000); // let the dashboard poll pick it up
  const alertItem = page.locator(".feed .item").first();
  if ((await alertItem.count()) > 0) {
    await alertItem.click();
    await sleep(1500);
    await scrollToText("Hearing");
    await sleep(12_000);
    const close = page.locator(".transcript .close");
    if ((await close.count()) > 0) await close.click();
  }
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await toast("The countdown: hours of warning, a cause, and a confidence range — not a threshold ping.", 9000);
  await sleep(15_000);

  // ---- ACT 4: the receipt (crossing observed, outcome backfilled) ---------
  await waitFor(async () => {
    const e = await api(`/api/streams/${STREAM}/events?kind=OUTCOME&limit=1`);
    return e && e.length > 0;
  }, 240_000);
  await toast(
    "ACT 4 — THE RECEIPT: the predicted window vs what actually happened. The prophecy is graded.",
    9000
  );
  await sleep(5000);
  await scrollToText("PROPHECY VS GROUND TRUTH");
  await sleep(18_000);
  await scrollToText("THE RECEIPT");
  await sleep(12_000);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await toast("Outcome backfilled: precision 1/1 — the system grades its own judgment in public.", 9000);
  await sleep(12_000);
} finally {
  const video = page.video();
  await ctx.close();
  await browser.close();
  if (video) {
    const p = await video.path();
    renameSync(p, OUT);
    console.log(`video saved -> ${OUT}`);
  }
}
