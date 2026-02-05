const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const url = process.argv[2];
const outputDir = process.argv[3] || '/tmp';

if (!url) {
  console.error('Usage: node scripts/capture-page.js <url> [output-dir]');
  console.error('Example: node scripts/capture-page.js http://localhost:3000/admin/index.html#/~/themes/agriculture');
  process.exit(1);
}

function buildPrefix(urlString) {
  const parsed = new URL(urlString);
  const domain = parsed.hostname.replace(/\./g, '-');
  const now = new Date();
  const timestamp = now.toISOString().replace(/[:T]/g, '-').replace(/\..+/, '');
  return `${domain}_${timestamp}`;
}

(async () => {
  const prefix = buildPrefix(url);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  console.log(`Navigating to: ${url}`);
  await page.goto(url, { waitUntil: 'networkidle' });

  // Capture screenshot
  const screenshotPath = path.join(outputDir, `${prefix}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`Screenshot saved: ${screenshotPath}`);

  // Capture rendered HTML
  const html = await page.content();
  const htmlPath = path.join(outputDir, `${prefix}.html`);
  fs.writeFileSync(htmlPath, html);
  console.log(`Rendered HTML saved: ${htmlPath}`);

  await browser.close();
})();
