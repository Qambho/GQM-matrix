/** GQM Matrix — documentation page renderer */

let docsLoaded = false;
let docsLoading = false;

function slugifyHeading(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

function stripMarkdownInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1");
}

function extractDocHeadings(markdown) {
  const headings = [];
  for (const line of markdown.split("\n")) {
    const match = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (!match) continue;
    const level = match[1].length;
    const text = stripMarkdownInline(match[2].trim());
    if (text.toLowerCase() === "table of contents") continue;
    headings.push({ level, text, id: slugifyHeading(text) });
  }
  return headings;
}

function buildDocsToc(headings) {
  const nav = document.getElementById("docs-toc-nav");
  if (!nav) return;

  if (!headings.length) {
    nav.innerHTML = `<span class="muted-block">No sections found.</span>`;
    return;
  }

  nav.innerHTML = headings
    .map((h) => {
      const cls = h.level === 3 ? "docs-toc-link docs-toc-link-sub" : "docs-toc-link";
      return `<a class="${cls}" href="#${h.id}" data-doc-anchor="${h.id}">${h.text}</a>`;
    })
    .join("");

  nav.querySelectorAll("[data-doc-anchor]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      document.getElementById(link.dataset.docAnchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#${link.dataset.docAnchor}`);
    });
  });
}

function loadScriptOnce(src) {
  if (document.querySelector(`script[src="${src}"]`)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.crossOrigin = "anonymous";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function ensureDocsLibraries() {
  await loadScriptOnce("https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js");
  try {
    await loadScriptOnce("https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js");
    await loadScriptOnce("https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js");
  } catch {
    /* math rendering optional */
  }
}

function renderMarkdown(html, markdown) {
  if (window.marked?.parse) {
    try {
      marked.use({
        renderer: {
          heading({ tokens, depth }) {
            const text = this.parser.parseInline(tokens);
            const plain = stripMarkdownInline(text.replace(/<[^>]+>/g, ""));
            return `<h${depth} id="${slugifyHeading(plain)}">${text}</h${depth}>`;
          },
        },
        gfm: true,
      });
      return marked.parse(markdown);
    } catch {
      /* fall through */
    }
  }
  return `<pre class="docs-fallback">${markdown.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</pre>`;
}

function typesetDocsMath(root) {
  if (typeof renderMathInElement === "function") {
    renderMathInElement(root, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
      strict: "ignore",
    });
  }
}

async function loadDocumentationPage() {
  if (docsLoaded || docsLoading) return;
  docsLoading = true;

  const contentEl = document.getElementById("docs-content");
  const tocNav = document.getElementById("docs-toc-nav");
  if (!contentEl) {
    docsLoading = false;
    return;
  }

  contentEl.innerHTML = `<p class="muted-block">Loading documentation…</p>`;

  try {
    const response = await fetch("/api/docs");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const markdown = await response.text();

    await ensureDocsLibraries();

    const headings = extractDocHeadings(markdown);
    buildDocsToc(headings);

    contentEl.innerHTML = renderMarkdown(contentEl.innerHTML, markdown);
    typesetDocsMath(contentEl);
    docsLoaded = true;
  } catch (error) {
    contentEl.innerHTML = `<div class="docs-error">
      <p class="rose">Failed to load documentation.</p>
      <p class="muted-block">${error.message}</p>
      <p class="muted-block">Restart the server so <code>/api/docs</code> is available, then refresh.</p>
    </div>`;
    if (tocNav) tocNav.innerHTML = `<span class="muted-block">Unavailable</span>`;
  } finally {
    docsLoading = false;
  }
}

window.loadDocumentationPage = loadDocumentationPage;
