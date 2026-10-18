// RAG Learning Path — lesson order, navigation and progress.
// Every lesson page has <body data-lesson="NN">; the index page has <body data-page="index">.
// Progress ("mark as learned") is kept in this browser only (localStorage).
(function () {
  const STAGES = {
    1: { name: "Foundations", why: "How language models read, represent and generate text — the base for everything else.", color: "var(--s1)" },
    2: { name: "Ingestion pipeline", why: "Turning raw files into clean, chunked, embedded and indexed knowledge.", color: "var(--s2)" },
    3: { name: "Retrieval & answers", why: "From a user's question to a grounded, cited answer.", color: "var(--s3)" },
    4: { name: "Quality", why: "Measure retrieval and answers before you change anything.", color: "var(--s4)" },
    5: { name: "Safety & production", why: "Make it safe, private, reliable and affordable — then put it all together.", color: "var(--s5)" },
  };

  const LESSONS = [
    ["01", "how-llms-work", "How LLMs work: the big picture", 1, 15, "Next-token prediction, training stages, base vs instruct models, what a model can and cannot know."],
    ["02", "tokens", "Tokens & tokenization", 1, 15, "How text becomes tokens, why token counts drive cost, latency and context limits."],
    ["03", "embeddings", "Embeddings & vector similarity", 1, 20, "Meaning as numbers: vectors, cosine similarity, dimensions and normalization."],
    ["04", "transformer", "Transformer architecture", 1, 30, "Self-attention, Q/K/V, multi-head attention, positions, decoder-only models and the KV cache."],
    ["05", "generation", "Generation & decoding", 1, 20, "Temperature, top-p, top-k, stop sequences, streaming and structured output."],
    ["06", "local-models", "Running models locally", 1, 25, "Quantization, VRAM math, Ollama vs vLLM vs llama.cpp, throughput and gateways."],
    ["07", "prompting", "Prompt engineering & structured output", 1, 25, "Roles, instructions, few-shot, reasoning, JSON output and prompt versioning."],
    ["08", "rag-fundamentals", "RAG fundamentals", 2, 20, "Why retrieval-augmented generation, when not to use it, and where RAG systems fail."],
    ["09", "parsing-ocr", "Document parsing & OCR", 2, 25, "PDF internals, layout and tables, Docling and PyMuPDF, OCR and quality checks."],
    ["10", "cleaning-metadata", "Cleaning, normalization & metadata", 2, 15, "Deduplication, boilerplate, language, metadata and provenance that retrieval can use."],
    ["11", "chunking", "Chunking", 2, 25, "Fixed, recursive, structure-aware, semantic and parent-child chunking — and how to choose."],
    ["12", "embedding-models", "Embedding models for retrieval", 2, 25, "Bi-encoders, choosing a model, query/passage prefixes, dimensions, versioning."],
    ["13", "vector-indexing", "Vector indexing & ANN search", 2, 25, "HNSW, recall vs speed, filters, quantization and how Qdrant stores vectors."],
    ["14", "lexical-search", "Lexical search & BM25", 2, 20, "Inverted indexes, BM25 scoring, analyzers and when keywords beat vectors."],
    ["15", "query-understanding", "Query understanding & transformation", 3, 20, "Normalization, classification, rewriting, multi-query, HyDE and decomposition."],
    ["16", "hybrid-fusion", "Hybrid search & rank fusion", 3, 20, "Combining dense and BM25 results with RRF or weighted fusion."],
    ["17", "reranking", "Reranking", 3, 20, "Cross-encoders, late interaction, LLM rerankers, MMR and the cost/quality trade-off."],
    ["18", "grounded-generation", "Context assembly & grounded generation", 3, 25, "Token budgets, ordering, citations, abstention and answer validation."],
    ["19", "advanced-rag", "Advanced RAG: agents, tools & graphs", 3, 30, "Tool calling, agentic and corrective RAG, multi-hop, GraphRAG and MCP — and when to use them."],
    ["20", "evaluation", "Evaluating RAG", 4, 30, "Golden datasets, retrieval metrics, faithfulness, LLM-as-judge and regression gates."],
    ["21", "observability", "Observability & tracing", 4, 20, "Traces and spans, latency breakdowns, token cost, logging policy and alerts."],
    ["22", "guardrails", "Guardrails", 5, 25, "Input, retrieval and output checks; refusals, moderation and grounding verification."],
    ["23", "security", "Security for LLM applications", 5, 30, "Prompt injection, data leakage, excessive agency and the OWASP Top 10 for LLMs."],
    ["24", "privacy-governance", "Privacy & data governance", 5, 20, "PII, access control, retention, deletion and audit trails."],
    ["25", "production", "Production engineering", 5, 30, "Caching, latency budgets, cost, scaling, index versioning and reliability."],
    ["26", "fine-tuning", "Fine-tuning & model adaptation", 5, 25, "When to fine-tune, LoRA/QLoRA, adapting embedders and rerankers, distillation."],
    ["27", "capstone", "Capstone: the complete system", 5, 30, "Every concept mapped onto the platform, plus a build and readiness checklist."],
  ].map(([id, slug, title, stage, minutes, summary]) => ({ id, slug, title, stage, minutes, summary, href: `${id}-${slug}.html` }));

  const KEY = "rag-learning-path:learned";
  const THEME_KEY = "rag-learning-path:theme";
  const load = () => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { return new Set(); } };
  const save = (set) => { try { localStorage.setItem(KEY, JSON.stringify([...set])); } catch { /* storage unavailable: progress is per page view only */ } };
  const learned = load();

  try { const t = localStorage.getItem(THEME_KEY); if (t) document.documentElement.dataset.theme = t; } catch { /* ignore */ }

  const el = (tag, attrs = {}, html = "") => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (html) e.innerHTML = html;
    return e;
  };

  function progressHtml() {
    const pct = Math.round((learned.size / LESSONS.length) * 100);
    return `<span>${learned.size} / ${LESSONS.length} learned</span><span class="bar"><i style="width:${pct}%"></i></span>`;
  }

  function topbar(crumb) {
    const bar = el("header", { class: "topbar" });
    bar.innerHTML = `
      <button class="menu-btn" type="button" aria-label="Show lessons">☰</button>
      <a class="brand" href="index.html">RAG Learning Path</a>
      <span class="crumb">${crumb}</span>
      <span class="spacer"></span>
      <span class="prog">${progressHtml()}</span>
      <button class="theme" type="button" title="Toggle light / dark">Theme</button>`;
    bar.querySelector(".menu-btn").addEventListener("click", () => document.body.classList.toggle("menu-open"));
    bar.querySelector(".theme").addEventListener("click", () => {
      const root = document.documentElement;
      const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem(THEME_KEY, root.dataset.theme); } catch { /* ignore */ }
    });
    return bar;
  }

  function sidebar(currentId) {
    const nav = el("nav", { class: "sidebar", "aria-label": "Lessons in order" });
    let stage = 0, html = `<a class="item" href="index.html"><span class="n">⌂</span><span>Start here · the path</span></a>`;
    for (const l of LESSONS) {
      if (l.stage !== stage) {
        stage = l.stage;
        html += `<div class="stage" style="color:${STAGES[stage].color}">Stage ${stage} · ${STAGES[stage].name}</div>`;
      }
      html += `<a class="item${l.id === currentId ? " current" : ""}" href="${l.href}"><span class="n">${l.id}</span><span>${l.title}</span>${learned.has(l.id) ? '<span class="done">✓</span>' : ""}</a>`;
    }
    nav.innerHTML = html;
    return nav;
  }

  function lessonPage(id) {
    const i = LESSONS.findIndex((l) => l.id === id);
    const l = LESSONS[i], prev = LESSONS[i - 1], next = LESSONS[i + 1];
    const st = STAGES[l.stage];
    document.title = `${l.id} · ${l.title} — RAG Learning Path`;

    const main = document.querySelector("main");
    const article = main.querySelector("article");
    const hero = el("header", { class: "hero" });
    const prereq = prev ? `<a href="${prev.href}">${prev.id} · ${prev.title}</a>` : "none — start here";
    hero.innerHTML = `
      <span class="stage-chip" style="background:${st.color}">Stage ${l.stage} · ${st.name}</span>
      <h1>${l.id} · ${l.title}</h1>
      <p class="lead">${l.summary}</p>
      <div class="meta"><span><b>Lesson ${i + 1}</b> of ${LESSONS.length}</span><span>⏱ about <b>${l.minutes} min</b></span><span>Before this: ${prereq}</span></div>`;
    article.prepend(hero);

    const pager = el("nav", { class: "pager", "aria-label": "Previous and next lesson" });
    pager.innerHTML = `
      ${prev ? `<a class="prev" href="${prev.href}"><small>← Previous</small>${prev.id} · ${prev.title}</a>` : `<a class="prev" href="index.html"><small>← Back</small>The learning path</a>`}
      <button class="learned" type="button"></button>
      ${next ? `<a class="next" href="${next.href}"><small>Next →</small>${next.id} · ${next.title}</a>` : `<a class="next" href="index.html"><small>Finished →</small>Back to the path</a>`}`;
    article.append(pager);
    const btn = pager.querySelector(".learned");
    const paint = () => { const on = learned.has(id); btn.classList.toggle("on", on); btn.textContent = on ? "✓ Learned" : "Mark as learned"; };
    btn.addEventListener("click", () => {
      learned.has(id) ? learned.delete(id) : learned.add(id);
      save(learned); paint();
      document.querySelector(".topbar .prog").innerHTML = progressHtml();
      const item = document.querySelector(".sidebar a.item.current");
      if (item) { item.querySelector(".done")?.remove(); if (learned.has(id)) item.insertAdjacentHTML("beforeend", '<span class="done">✓</span>'); }
    });
    paint();

    const shell = el("div", { class: "shell" });
    main.replaceWith(shell);
    shell.append(sidebar(id), main);
    document.body.prepend(topbar(`Stage ${l.stage} · ${st.name} › ${l.title}`));

    addEventListener("keydown", (e) => {
      if (/input|textarea|select/i.test(e.target.tagName)) return;
      if (e.key === "ArrowLeft" && prev) location.href = prev.href;
      if (e.key === "ArrowRight" && next) location.href = next.href;
    });
    // centre the current lesson inside the sidebar only (scrollIntoView would also scroll the page)
    requestAnimationFrame(() => {
      const nav = document.querySelector(".sidebar"), item = nav && nav.querySelector("a.item.current");
      if (item) nav.scrollTop = item.offsetTop - nav.clientHeight / 2 + item.offsetHeight / 2;
    });
  }

  function indexPage() {
    const host = document.getElementById("path");
    const nextUp = LESSONS.find((l) => !learned.has(l.id)) || LESSONS[0];
    const cont = document.getElementById("continue");
    if (cont) { cont.href = nextUp.href; cont.textContent = learned.size ? `Continue: ${nextUp.id} · ${nextUp.title}` : `Start: 01 · ${LESSONS[0].title}`; }
    const total = LESSONS.reduce((a, l) => a + l.minutes, 0);
    const tm = document.getElementById("total-time");
    if (tm) tm.textContent = `${LESSONS.length} lessons · about ${Math.round(total / 60)} hours in total`;
    for (const [n, st] of Object.entries(STAGES)) {
      const items = LESSONS.filter((l) => l.stage === +n);
      const block = el("section", { class: "stage-block" });
      block.innerHTML = `<h2 style="color:${st.color}">Stage ${n} · ${st.name}</h2><div class="why">${st.why}</div>
        <div class="lesson-list">${items.map((l) => `
          <a class="lesson-card" href="${l.href}">
            <span class="n" style="background:${st.color}">${l.id}</span>
            <span><span class="tt">${l.title}</span><span class="sm" style="display:block">${l.summary}</span></span>
            <span class="st${learned.has(l.id) ? " ok" : ""}">${learned.has(l.id) ? "✓ learned" : l.minutes + " min"}</span>
          </a>`).join("")}</div>`;
      host.append(block);
    }
    document.body.prepend(topbar("Start here — the order to learn everything"));
    document.querySelector(".menu-btn").style.display = "none";
  }

  window.RAG_PATH = { LESSONS, STAGES };
  document.addEventListener("DOMContentLoaded", () => {
    const id = document.body.dataset.lesson;
    if (id) lessonPage(id);
    else if (document.body.dataset.page === "index") indexPage();
  });
})();
