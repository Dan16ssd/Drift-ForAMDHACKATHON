/* Screenshot pitch-audio/titlecard.html to a 1920x1080 PNG for the pitch video. */
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto("file://" + path.join(root, "pitch-audio", "titlecard.html"));
await page.waitForTimeout(500); // let the SVG render
await page.screenshot({ path: path.join(root, "pitch-audio", "titlecard.png") });
await browser.close();
console.log("wrote pitch-audio/titlecard.png");
