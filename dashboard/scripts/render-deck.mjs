/* Render deck/deck.html to deck/DRIFT-deck.pdf (1920x1080 pages, one per slide).
   Canva imports the PDF with each page as an editable design. */
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const browser = await chromium.launch({ headless: true }); // bundled chromium: page.pdf support
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto("file://" + path.join(root, "deck", "deck.html"));
await page.waitForTimeout(600); // let the SVG logo render
await page.pdf({
  path: path.join(root, "deck", "DRIFT-deck.pdf"),
  width: "1920px",
  height: "1080px",
  printBackground: true,
});
const slides = page.locator(".slide");
const n = await slides.count();
for (let i = 0; i < n; i++) {
  await slides.nth(i).screenshot({
    path: path.join(root, "deck", `slide-${String(i + 1).padStart(2, "0")}.png`),
  });
}
await browser.close();
console.log(`wrote deck/DRIFT-deck.pdf + ${n} slide PNGs`);
