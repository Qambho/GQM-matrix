/** GQM Matrix — section-based documentation viewer */

const docsState = {
  loaded: false,
  loading: false,
  activeId: "overview",
  overview: null,
  sections: [],
};

function slugifyHeading(text) {
  return stripInline(text)
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

function stripInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1");
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(text) {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return out;
}

function parseDocumentation(markdown) {
  const lines = markdown.split("\n");
  const overviewLines = [];
  const sections = [];
  let inToc = false;
  let current = null;

  for (const line of lines) {
    if (/^##\s+Table of Contents/i.test(line)) {
      inToc = true;
      continue;
    }
    if (inToc) {
      if (/^---\s*$/.test(line.trim())) inToc = false;
      continue;
    }

    const h2 = /^##\s+(.+)$/.exec(line);
    if (h2) {
      if (current) sections.push(current);
      const title = stripInline(h2[1].trim());
      current = { id: slugifyHeading(title), title, lines: [] };
      continue;
    }

    if (current) current.lines.push(line);
    else overviewLines.push(line);
  }
  if (current) sections.push(current);

  const overviewMarkdown = overviewLines.join("\n").trim();
  const overviewTitle =
    /^#\s+(.+)$/m.exec(overviewMarkdown)?.[1]?.replace(/\*\*/g, "") || "Overview";

  return {
    overview: {
      id: "overview",
      title: stripInline(overviewTitle),
      markdown: overviewMarkdown,
    },
    sections: sections.map((s) => ({
      id: s.id,
      title: s.title,
      markdown: s.lines.join("\n").trim(),
    })),
  };
}

function mdToHtml(markdown) {
  const lines = markdown.split("\n");
  const parts = [];
  let paragraph = [];
  let listItems = [];
  let listOrdered = false;
  let inCode = false;
  let codeLines = [];
  let tableRows = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    parts.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    const tag = listOrdered ? "ol" : "ul";
    parts.push(`<${tag}>${listItems.map((li) => `<li>${inlineMarkdown(li)}</li>`).join("")}</${tag}>`);
    listItems = [];
    listOrdered = false;
  };

  const flushTable = () => {
    if (tableRows.length < 2) {
      tableRows = [];
      return;
    }
    const [header, , ...body] = tableRows;
    const headerCells = header.split("|").filter(Boolean).map((c) => c.trim());
    const bodyHtml = body
      .map((row) => {
        const cells = row.split("|").filter(Boolean).map((c) => `<td>${inlineMarkdown(c.trim())}</td>`);
        return `<tr>${cells.join("")}</tr>`;
      })
      .join("");
    const headHtml = headerCells.map((c) => `<th>${inlineMarkdown(c)}</th>`).join("");
    parts.push(`<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`);
    tableRows = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      flushTable();
      if (!inCode) {
        inCode = true;
        codeLines = [];
      } else {
        parts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        inCode = false;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (trimmed.startsWith("|")) {
      flushParagraph();
      flushList();
      tableRows.push(trimmed);
      continue;
    }
    flushTable();

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushList();
      parts.push("<hr />");
      continue;
    }

    const h3 = /^###\s+(.+)$/.exec(line);
    if (h3) {
      flushParagraph();
      flushList();
      const id = slugifyHeading(h3[1]);
      parts.push(`<h3 id="${id}">${inlineMarkdown(h3[1])}</h3>`);
      continue;
    }

    const h2 = /^##\s+(.+)$/.exec(line);
    if (h2) {
      flushParagraph();
      flushList();
      parts.push(`<h2>${inlineMarkdown(h2[1])}</h2>`);
      continue;
    }

    const h1 = /^#\s+(.+)$/.exec(line);
    if (h1) {
      flushParagraph();
      flushList();
      parts.push(`<h1>${inlineMarkdown(h1[1])}</h1>`);
      continue;
    }

    const ol = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ol) {
      flushParagraph();
      if (!listOrdered && listItems.length) flushList();
      listOrdered = true;
      listItems.push(ol[1]);
      continue;
    }

    const ul = /^[-*]\s+(.+)$/.exec(trimmed);
    if (ul) {
      flushParagraph();
      if (listOrdered && listItems.length) flushList();
      listOrdered = false;
      listItems.push(ul[1]);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  flushTable();
  if (inCode && codeLines.length) {
    parts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }

  return parts.join("\n");
}

function allDocSections() {
  return [docsState.overview, ...docsState.sections].filter(Boolean);
}

function getSectionById(id) {
  return allDocSections().find((s) => s.id === id) || docsState.overview;
}

function buildDocsToc() {
  const nav = document.getElementById("docs-toc-nav");
  if (!nav) return;

  const items = allDocSections();
  nav.innerHTML = items
    .map(
      (s) =>
        `<button type="button" class="docs-toc-link${s.id === docsState.activeId ? " active" : ""}" data-doc-section="${s.id}">${s.title}</button>`,
    )
    .join("");

  nav.querySelectorAll("[data-doc-section]").forEach((btn) => {
    btn.addEventListener("click", () => showDocSection(btn.dataset.docSection));
  });
}

function updateDocHeader(section) {
  const titleEl = document.getElementById("docs-section-title");
  const badgeEl = document.getElementById("docs-section-badge");
  const indexEl = document.getElementById("docs-section-index");
  const items = allDocSections();
  const idx = items.findIndex((s) => s.id === section.id);

  if (titleEl) titleEl.textContent = section.title;
  if (badgeEl) badgeEl.textContent = section.id === "overview" ? "Guide" : "Formula Reference";
  if (indexEl) indexEl.textContent = `${idx + 1} / ${items.length}`;
}

function updateDocNavButtons() {
  const items = allDocSections();
  const idx = items.findIndex((s) => s.id === docsState.activeId);
  const prevBtn = document.getElementById("docs-prev-btn");
  const nextBtn = document.getElementById("docs-next-btn");

  if (prevBtn) {
    prevBtn.disabled = idx <= 0;
    prevBtn.onclick = () => idx > 0 && showDocSection(items[idx - 1].id);
  }
  if (nextBtn) {
    nextBtn.disabled = idx >= items.length - 1;
    nextBtn.onclick = () => idx < items.length - 1 && showDocSection(items[idx + 1].id);
  }
}

function typesetDocsMath(root) {
  if (typeof renderMathInElement !== "function") return;
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

function showDocSection(id) {
  const section = getSectionById(id);
  if (!section) return;

  docsState.activeId = section.id;
  const contentEl = document.getElementById("docs-content");
  if (!contentEl) return;

  contentEl.innerHTML = mdToHtml(section.markdown);
  typesetDocsMath(contentEl);

  updateDocHeader(section);
  buildDocsToc();
  updateDocNavButtons();

  const pageContent = document.querySelector(".page-content");
  if (pageContent) pageContent.scrollTop = 0;
}

async function loadScriptOnce(src) {
  if (document.querySelector(`script[src="${src}"]`)) return;
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.crossOrigin = "anonymous";
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

async function ensureKatex() {
  try {
    await loadScriptOnce("https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js");
    await loadScriptOnce("https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js");
  } catch {
    /* math optional */
  }
}

async function loadDocumentationPage() {
  if (docsState.loaded || docsState.loading) {
    if (docsState.loaded) showDocSection(docsState.activeId);
    return;
  }
  docsState.loading = true;

  const contentEl = document.getElementById("docs-content");
  const tocNav = document.getElementById("docs-toc-nav");
  if (!contentEl) {
    docsState.loading = false;
    return;
  }

  contentEl.innerHTML = `<p class="muted-block">Loading documentation…</p>`;

  try {
    const response = await fetch("/api/docs");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const markdown = await response.text();

    await ensureKatex();

    const parsed = parseDocumentation(markdown);
    docsState.overview = parsed.overview;
    docsState.sections = parsed.sections;
    docsState.loaded = true;

    showDocSection("overview");
  } catch (error) {
    contentEl.innerHTML = `<div class="docs-error">
      <p class="rose">Failed to load documentation.</p>
      <p class="muted-block">${escapeHtml(error.message)}</p>
    </div>`;
    if (tocNav) tocNav.innerHTML = `<span class="muted-block">Unavailable</span>`;
  } finally {
    docsState.loading = false;
  }
}

window.loadDocumentationPage = loadDocumentationPage;
window.showDocSection = showDocSection;
