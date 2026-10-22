/* RAG Handbook — builds every section page and the start page from data/NN.js.
   Section pages: <body data-section="NN">. Start page: <body data-page="index">.
   Data files call HB.add({ id, intro, groups: [{ id, title, items: [{ t, s, h, u, p, e, c, l, n }] }] }). */
(function () {
  "use strict";

  // [id, file slug, title, one-line summary, part] — in learning order: the numbers are the path.
  const SECTIONS = [
    ["01", "llm-core", "LLM Core & Architecture", "Transformers, tokens, attention, decoding, serving", "Foundations"],
    ["02", "foundation", "RAG Foundation", "What RAG is, LLM basics and information-retrieval basics", "Foundations"],
    ["03", "ingestion", "Data Ingestion", "Sources, connectors, sync, deduplication, governance", "Offline pipeline"],
    ["04", "parsing", "Parsing", "Text extraction, layout, tables, images and special content", "Offline pipeline"],
    ["05", "chunking", "Chunking", "Splitting documents into searchable pieces, and enriching them", "Offline pipeline"],
    ["06", "embedding", "Embedding", "Turning text into vectors: types, maths, models, optimization", "Offline pipeline"],
    ["07", "indexing", "Indexing", "Vector stores, ANN algorithms, filtering, index operations", "Offline pipeline"],
    ["08", "query-understanding", "User Query Understanding", "Intent, routing and conversational context", "Online pipeline"],
    ["09", "query-rewriting", "Query Rewriting", "Reformulation, expansion and decomposition", "Online pipeline"],
    ["10", "query-assembly", "Query Assembly", "Filters, permissions, text-to-SQL, search parameters", "Online pipeline"],
    ["11", "retrieval", "Retrieval", "Core and advanced retrieval techniques", "Online pipeline"],
    ["12", "hybrid", "Hybrid Retrieval", "Fusing dense and keyword results", "Online pipeline"],
    ["13", "reranking", "Reranking", "Second-stage models and reranking strategies", "Online pipeline"],
    ["14", "context-assembly", "Context Assembly", "Selecting, compressing and prompting with evidence", "Online pipeline"],
    ["15", "context-window", "Context Window Handling", "Token budgets, truncation and long-context behaviour", "Online pipeline"],
    ["16", "memory", "Memory", "Short- and long-term memory for assistants", "Online pipeline"],
    ["17", "generation", "LLM Generation", "Grounded answering and generation controls", "Online pipeline"],
    ["18", "advanced-rag", "Advanced RAG Architectures", "Self-correcting, agentic, graph and structured RAG", "Advanced RAG"],
    ["19", "guardrails-security", "Guardrails & Security", "Input, data and output protection", "Quality & safety"],
    ["20", "evaluation", "Evaluation", "Retrieval metrics, generation metrics, evaluation methods", "Quality & safety"],
    ["21", "production-ops", "Production & Ops", "Observability, performance, cost, lifecycle", "Production"],
    ["22", "system-architecture", "RAG System Architecture", "Patterns, components, data, scale, security, trade-offs", "Production"],
    ["23", "fine-tuning", "Fine-tuning", "Training stages, LoRA, preference optimization, fine-tuning for RAG", "Specialise"],
    ["24", "tools", "Tools & Frameworks", "The ecosystem and when to use each tool", "Ecosystem"],
  ];
  const ORDER = SECTIONS.map((s) => s[0]);

  const data = {};
  // A big section may be split over several data files (NN.js, NN-2.js…): their groups are appended in order.
  window.HB = {
    add(section) {
      if (data[section.id]) data[section.id].groups.push(...section.groups);
      else data[section.id] = section;
    },
    SECTIONS,
  };

  const byId = (id) => SECTIONS.find((s) => s[0] === id);
  const fileOf = (id) => `${id}-${byId(id)[1]}.html`;
  const anchor = (cid) => "c" + cid.replace(/\./g, "-");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const plain = (html) => String(html || "").replace(/<[^>]+>/g, "");
  const el = (tag, attrs = {}, html = "") => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (html) node.innerHTML = html;
    return node;
  };
  const count = (id) => (data[id] ? data[id].groups.reduce((n, g) => n + g.items.length, 0) : 0);

  function topbar(crumb) {
    const bar = el("header", { class: "topbar" });
    bar.innerHTML = `<button class="menu-btn" type="button" aria-label="Show sections">☰</button>
      <a class="brand" href="index.html">RAG Handbook</a>
      <span class="crumb">${esc(crumb)}</span><span class="spacer"></span>
      <a class="tlink" href="../concepts/rag-flow.html">Production flow</a>`;
    bar.querySelector(".menu-btn").addEventListener("click", () => document.body.classList.toggle("menu-open"));
    return bar;
  }

  function sidebar(currentId) {
    const nav = el("nav", { class: "sidebar", "aria-label": "Handbook sections" });
    let html = `<a class="item${currentId ? "" : " current"}" href="index.html"><span class="n">⌂</span><span>Start here · all concepts</span></a>`;
    let part = "";
    for (const [id, , title, , p] of SECTIONS) {
      if (p !== part) { part = p; html += `<div class="stage">${esc(p)}</div>`; }
      html += `<a class="item${id === currentId ? " current" : ""}" href="${fileOf(id)}"><span class="n">${id}</span><span>${esc(title)}</span></a>`;
      if (id === currentId && data[id]) {
        html += `<div class="subnav">` + data[id].groups.map((g) => `<a href="#g${g.id.replace(/\./g, "-")}">${esc(g.id)} ${esc(g.title)}</a>`).join("") + `</div>`;
      }
    }
    nav.innerHTML = html;
    nav.addEventListener("click", (e) => { if (e.target.closest("a")) document.body.classList.remove("menu-open"); });
    return nav;
  }

  function shell(currentId, crumb) {
    const main = document.querySelector("main");
    const wrap = el("div", { class: "shell" });
    main.replaceWith(wrap);
    wrap.append(sidebar(currentId), main);
    document.body.prepend(topbar(crumb));
    const cur = document.querySelector(".sidebar a.item.current");
    if (cur) cur.scrollIntoView({ block: "center" });
  }

  const LABELS = [["h", "How it works"], ["u", "Where to use it"], ["p", "Real-world problem it solves"], ["e", "Real-time example"], ["n", "Watch out"]];

  function conceptCard(item, cid) {
    const card = el("article", { class: "concept", id: anchor(cid) });
    card.dataset.search = (item.t + " " + plain(item.s) + " " + plain(item.h)).toLowerCase();
    let html = `<h3><span class="cid">${cid}</span><span>${esc(item.t)}</span><a class="self" href="#${anchor(cid)}" aria-label="Link to ${esc(item.t)}">#</a></h3>`;
    if (item.s) html += `<p class="lead"><span class="lbl">In simple words</span>${item.s}</p>`;
    html += "<dl>" + LABELS.filter(([k]) => item[k]).map(([k, label]) => `<dt class="k-${k}">${label}</dt><dd>${item[k]}</dd>`).join("") + "</dl>";
    card.innerHTML = html;
    if (item.c) {
      const box = el("div", { class: "code" });
      box.innerHTML = `<div class="code-h"><span>Simple code · ${esc(item.l || "python")}</span><button type="button">Copy</button></div>`;
      const pre = el("pre"), code = el("code");
      code.textContent = item.c.replace(/^\n+|\s+$/g, "");
      pre.append(code); box.append(pre); card.append(box);
      box.querySelector("button").addEventListener("click", (e) => {
        const done = () => { e.target.textContent = "Copied"; setTimeout(() => (e.target.textContent = "Copy"), 1200); };
        try { navigator.clipboard.writeText(code.textContent).then(done, () => {}); } catch (err) { /* clipboard blocked */ }
      });
    }
    return card;
  }

  function sectionPage(id) {
    const meta = byId(id), d = data[id];
    document.title = `${meta[2]} — RAG Handbook`;
    shell(id, `${id} · ${meta[2]}`);
    const host = document.getElementById("hb");
    if (!d) { host.innerHTML = `<p>This section's data file did not load.</p>`; return; }
    const pos = ORDER.indexOf(id);
    host.innerHTML = `<div class="hero"><span class="stage-chip" style="background:var(--accent)">${esc(meta[4])} · section ${id}</span>
      <h1>${esc(meta[2])}</h1><p class="lead">${d.intro || esc(meta[3])}</p>
      <div class="meta"><span><b>${count(id)}</b> concepts</span><span><b>${d.groups.length}</b> groups</span><span>learning step <b>${pos + 1}</b> of ${ORDER.length}</span></div></div>
      <div class="finder"><input type="search" placeholder="Filter the concepts on this page…" aria-label="Filter concepts"><span class="hits"></span></div>`;
    for (const g of d.groups) {
      const block = el("section", { class: "group", id: "g" + g.id.replace(/\./g, "-") });
      block.innerHTML = `<h2><span class="ix">${esc(g.id)}</span>${esc(g.title)}</h2>${g.intro ? `<p class="gintro">${g.intro}</p>` : ""}`;
      g.items.forEach((item, i) => block.append(conceptCard(item, `${g.id}.${i + 1}`)));
      host.append(block);
    }
    const prev = ORDER[pos - 1], next = ORDER[pos + 1];
    host.append(el("nav", { class: "pager" },
      (prev ? `<a href="${fileOf(prev)}"><small>Previous in the learning order</small>${prev} · ${esc(byId(prev)[2])}</a>` : `<a href="index.html"><small>Back</small>Start page</a>`) +
      (next ? `<a class="next" href="${fileOf(next)}"><small>Next in the learning order</small>${next} · ${esc(byId(next)[2])}</a>` : `<a class="next" href="index.html"><small>Finished</small>Start page</a>`)));
    const input = host.querySelector(".finder input"), hits = host.querySelector(".finder .hits");
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0;
      host.querySelectorAll(".concept").forEach((c) => { const ok = !q || c.dataset.search.includes(q); c.hidden = !ok; shown += ok; });
      host.querySelectorAll(".group").forEach((g) => { g.hidden = !g.querySelector(".concept:not([hidden])"); });
      hits.textContent = q ? `${shown} of ${count(id)}` : "";
    });
    if (location.hash) requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView());
  }

  function indexPage() {
    shell(null, "Every RAG concept, explained simply");
    const host = document.getElementById("hb");
    const total = SECTIONS.reduce((n, s) => n + count(s[0]), 0);
    host.innerHTML = `<div class="hero"><span class="stage-chip" style="background:var(--accent)">RAG Handbook</span>
      <h1>Every RAG concept, explained simply</h1>
      <p class="lead">${total} concepts in ${SECTIONS.length} sections — from what RAG is to fine-tuning and system design. Each concept: <b>in simple words</b>, <b>how it works</b>, <b>where to use it</b>, <b>the real-world problem it solves</b>, a <b>real-time example</b> and, where it helps, <b>simple code</b>.</p></div>
      <div class="finder big"><input type="search" placeholder="Search all ${total} concepts — try “BM25”, “LoRA”, “prompt injection”…" aria-label="Search all concepts"><span class="hits"></span></div>
      <div class="results"></div>
      <h2>Suggested learning order</h2>
      <p>The section numbers are the learning path: how LLMs work, then RAG basics, then the pipeline in the order data flows, then safety, evaluation, production, architecture, fine-tuning and tools. The full production checklist is in <a href="../concepts/rag-flow.html">Production RAG flow</a>.</p>
      <ol class="order">${ORDER.map((id) => `<li><a href="${fileOf(id)}"><b>${id} · ${esc(byId(id)[2])}</b></a> <span>${esc(byId(id)[3])} · ${count(id)} concepts</span></li>`).join("")}</ol>
      <h2>The whole tree</h2><div class="tree"></div>`;
    const tree = host.querySelector(".tree");
    for (const [id, , title] of SECTIONS) {
      const d = data[id];
      const box = el("details", { class: "tsec" });
      box.innerHTML = `<summary><span class="n">${id}</span> ${esc(title)} <small>${count(id)} concepts</small></summary>` + (d ? d.groups.map((g) =>
        `<div class="tgroup"><b>${esc(g.id)} ${esc(g.title)}</b><ul>${g.items.map((it, i) => `<li><a href="${fileOf(id)}#${anchor(`${g.id}.${i + 1}`)}">${esc(it.t)}</a></li>`).join("")}</ul></div>`).join("") : "");
      tree.append(box);
    }
    const input = host.querySelector(".finder input"), hits = host.querySelector(".finder .hits"), results = host.querySelector(".results");
    const all = [];
    for (const [id] of SECTIONS) (data[id]?.groups || []).forEach((g) => g.items.forEach((it, i) => all.push({ id, cid: `${g.id}.${i + 1}`, it, hay: (it.t + " " + plain(it.s)).toLowerCase() })));
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (q.length < 2) { results.innerHTML = ""; hits.textContent = ""; return; }
      const found = all.filter((x) => x.hay.includes(q)).sort((a, b) => (b.it.t.toLowerCase().includes(q)) - (a.it.t.toLowerCase().includes(q)));
      hits.textContent = `${found.length} found`;
      results.innerHTML = found.slice(0, 40).map((x) => `<a class="hit" href="${fileOf(x.id)}#${anchor(x.cid)}"><span class="cid">${x.cid}</span><b>${esc(x.it.t)}</b><span>${x.it.s || ""}</span></a>`).join("") +
        (found.length > 40 ? `<p class="muted">Showing 40 of ${found.length}. Type more to narrow down.</p>` : "");
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const id = document.body.dataset.section;
    if (id) sectionPage(id);
    else if (document.body.dataset.page === "index") indexPage();
  });
})();
