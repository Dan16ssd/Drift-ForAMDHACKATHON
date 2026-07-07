/* Spot-check the recorded demo: report duration and screenshot frames.
 * Loads the webm directly in Chrome's media viewer (file:// video inside a
 * scripted page is blocked by default). Playwright webm has no duration
 * header, so we force a scan with the currentTime=1e10 trick. */
import { chromium } from "playwright";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = join(HERE, "..", "..", "assets", "demo.webm");
const OUTDIR = process.argv[2] || HERE;

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--allow-file-access-from-files", "--autoplay-policy=no-user-gesture-required"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto("file:///" + VIDEO.replace(/\\/g, "/"));
await page.waitForSelector("video");

const duration = await page.evaluate(() => {
  const v = document.querySelector("video");
  v.pause();
  return new Promise((res) => {
    if (Number.isFinite(v.duration) && v.duration > 0) return res(v.duration);
    v.ondurationchange = () => {
      if (Number.isFinite(v.duration) && v.duration > 0) res(v.duration);
    };
    v.currentTime = 1e10;
  });
});
console.log(`duration: ${duration.toFixed(1)}s`);

for (const frac of [0.05, 0.45, 0.62, 0.85, 0.97]) {
  const t = Math.min(duration * frac, duration - 0.5);
  await page.evaluate((t) => {
    const v = document.querySelector("video");
    return new Promise((res) => {
      v.onseeked = res;
      v.currentTime = t;
    });
  }, t);
  await page.screenshot({ path: join(OUTDIR, `frame_${Math.round(t)}s.png`) });
  console.log(`frame at ${t.toFixed(0)}s saved`);
}
await browser.close();
