/* Spot-check the recorded demo: report duration and screenshot frames. */
import { chromium } from "playwright";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = join(HERE, "..", "..", "assets", "demo.webm");
const OUTDIR = process.argv[2] || HERE;

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.setContent(
  `<body style="margin:0"><video id="v" width="1280" height="800" muted></video></body>`
);
await page.evaluate((src) => {
  const v = document.getElementById("v");
  v.src = src;
  return new Promise((res) => (v.onloadedmetadata = res));
}, "file:///" + VIDEO.replace(/\\/g, "/"));

const duration = await page.evaluate(() => document.getElementById("v").duration);
console.log(`duration: ${duration.toFixed(1)}s`);

for (const frac of [0.05, 0.45, 0.62, 0.85, 0.97]) {
  const t = duration * frac;
  await page.evaluate((t) => {
    const v = document.getElementById("v");
    return new Promise((res) => {
      v.onseeked = res;
      v.currentTime = t;
    });
  }, t);
  await page.screenshot({ path: join(OUTDIR, `frame_${Math.round(t)}s.png`) });
  console.log(`frame at ${t.toFixed(0)}s saved`);
}
await browser.close();
