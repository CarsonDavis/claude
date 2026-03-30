const { chromium } = require('playwright');
const { Readability } = require('@mozilla/readability');
const { JSDOM, VirtualConsole } = require('jsdom');
const TurndownService = require('turndown');
const fs = require('fs');
const path = require('path');

const url = process.argv[2];
const outputPath = process.argv[3]; // optional: full path for output file

if (!url) {
  console.error('Usage: node scripts/scrape-docs.js <url> [output-path]');
  console.error('Example: node scripts/scrape-docs.js https://docs.example.com/api/auth ./docs.md');
  process.exit(1);
}

// Configure turndown for clean markdown
function createTurndown() {
  const td = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
  });

  // Preserve code blocks with language hints
  td.addRule('fencedCodeBlock', {
    filter: (node) => {
      return (
        node.nodeName === 'PRE' &&
        node.querySelector('code')
      );
    },
    replacement: (content, node) => {
      const code = node.querySelector('code');
      const lang = (code.className || '').replace(/^language-/, '').split(' ')[0] || '';
      const text = code.textContent || '';
      return `\n\`\`\`${lang}\n${text.trim()}\n\`\`\`\n`;
    },
  });

  // Strip nav, sidebar, footer, and other non-content elements
  td.remove(['nav', 'footer', 'header', 'style', 'script', 'noscript']);

  return td;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  console.error(`Navigating to: ${url}`);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

  // Wait a beat for any client-side rendering to finish
  await page.waitForTimeout(1500);

  const html = await page.content();
  const pageTitle = await page.title();
  const finalUrl = page.url(); // in case of redirects

  await browser.close();

  // Use Readability to extract the main content
  // Suppress CSS parsing errors from jsdom (cosmetic, doesn't affect content extraction)
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('error', () => {});
  const dom = new JSDOM(html, { url: finalUrl, virtualConsole });
  const reader = new Readability(dom.window.document, {
    charThreshold: 100,
  });
  const article = reader.parse();

  if (!article) {
    console.error('ERROR: Readability could not extract content from this page.');
    console.error('The page may be behind a login wall, heavily JS-rendered, or have no main content.');
    process.exit(2);
  }

  // Convert to markdown
  const td = createTurndown();
  const markdown = td.turndown(article.content);

  // Build the output document
  const output = [
    `# ${article.title || pageTitle}`,
    '',
    `> **Source:** ${finalUrl}`,
    `> **Scraped:** ${new Date().toISOString().split('T')[0]}`,
    '',
    '---',
    '',
    markdown,
  ].join('\n');

  if (outputPath) {
    // Ensure output directory exists
    const dir = path.dirname(outputPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(outputPath, output);
    console.log(outputPath);
  } else {
    // Print to stdout
    console.log(output);
  }
})();
