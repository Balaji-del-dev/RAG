// RAG Learning Path — lesson order, navigation, progress, interview Q&A rendering.
// Lesson pages: <body data-lesson="NN">. Other pages: data-page="index" | "bank" | "revision".
// Interview questions and revision cards live in assets/qa/NN.js (window.QA[id]).
// Progress is kept in this browser only (localStorage).
(function () {
  const STAGES = {
    1: { name: "Foundations", why: "How language models read, understand and write text. Interviews almost always start here.", color: "var(--s1)" },
    2: { name: "Ingestion pipeline", why: "How raw files become clean, searchable knowledge: parsing, chunking, embeddings, indexes.", color: "var(--s2)" },
    3: { name: "Retrieval & answers", why: "How a question becomes a correct answer with sources: search, ranking, prompting.", color: "var(--s3)" },
    4: { name: "Quality", why: "How to prove the system works: evaluation metrics and tracing.", color: "var(--s4)" },
    5: { name: "Safety & production", why: "How to make it safe, private, fast and affordable — and explain the full system.", color: "var(--s5)" },
  };

  const LESSONS = [
    ["01", "how-llms-work", "How LLMs work", 1, 20, "What a large language model really does: predict the next word-piece, again and again."],
    ["02", "tokens", "Tokens & tokenization", 1, 20, "How text is cut into tokens, and why tokens decide cost, speed and limits."],
    ["03", "embeddings", "Embeddings & similarity", 1, 25, "How meaning becomes a list of numbers, and how we measure 'similar'."],
    ["04", "transformer", "Transformer & attention", 1, 35, "The architecture behind every modern LLM: self-attention, Q/K/V, layers, KV cache."],
    ["05", "generation", "Decoding: temperature, top-p", 1, 20, "How the model picks each next token, and the settings that control it."],
    ["06", "local-models", "Running models locally", 1, 25, "GPU memory, quantization, and serving engines like Ollama and vLLM."],
    ["07", "prompting", "Prompt engineering", 1, 25, "How to write prompts that work: roles, few-shot, chain-of-thought, JSON output."],
    ["08", "rag-fundamentals", "RAG fundamentals", 2, 25, "Retrieval-augmented generation: why it exists, how it works, where it fails."],
    ["09", "parsing-ocr", "Document parsing & OCR", 2, 20, "Getting clean text and tables out of PDFs, Office files and scans."],
    ["10", "cleaning-metadata", "Cleaning & metadata", 2, 15, "Removing noise and duplicates, and adding the labels search needs."],
    ["11", "chunking", "Chunking strategies", 2, 25, "How to cut documents into pieces that search well — and how to choose the size."],
    ["12", "embedding-models", "Embedding models", 2, 20, "How retrieval embedding models work and how to pick one."],
    ["13", "vector-indexing", "Vector databases & HNSW", 2, 25, "How vector search stays fast with millions of vectors: ANN, HNSW, filters, quantization."],
    ["14", "lexical-search", "Keyword search & BM25", 2, 20, "How classic keyword search works and why RAG still needs it."],
    ["15", "query-understanding", "Query transformation", 3, 20, "Fixing the question before searching: rewriting, multi-query, HyDE, decomposition."],
    ["16", "hybrid-fusion", "Hybrid search & RRF", 3, 20, "Combining vector and keyword search results with Reciprocal Rank Fusion."],
    ["17", "reranking", "Reranking", 3, 20, "Re-ordering candidates with a cross-encoder for much better precision."],
    ["18", "grounded-generation", "Grounded answers & hallucination", 3, 25, "Building the prompt context, citing sources, saying 'I don't know', checking answers."],
    ["19", "advanced-rag", "Agents, tools & GraphRAG", 3, 25, "Tool calling, agentic RAG, corrective RAG, GraphRAG and MCP — and when to use them."],
    ["20", "evaluation", "Evaluating RAG", 4, 30, "Golden datasets, retrieval metrics, faithfulness, LLM-as-a-judge, RAGAS."],
    ["21", "observability", "Observability & tracing", 4, 15, "Seeing inside every request: traces, spans, latency, tokens, alerts."],
    ["22", "guardrails", "Guardrails", 5, 20, "Checks around the model: input, retrieval, output and action guardrails."],
    ["23", "security", "LLM security & prompt injection", 5, 30, "Prompt injection, data leakage and the OWASP Top 10 for LLM applications."],
    ["24", "privacy-governance", "Privacy & data governance", 5, 15, "Personal data, access control, retention and complete deletion."],
    ["25", "production", "Production: latency, cost, scale", 5, 25, "Caching, latency budgets, async jobs, versioned indexes and cost control."],
    ["26", "fine-tuning", "Fine-tuning, LoRA & RLHF", 5, 25, "When to fine-tune vs use RAG, LoRA/QLoRA, RLHF/DPO and distillation."],
    ["27", "capstone", "System design: the full RAG system", 5, 30, "Explain and design a complete RAG system, end to end, like in a design interview."],
  ].map(([id, slug, title, stage, minutes, summary]) => ({ id, slug, title, stage, minutes, summary, href: `${id}-${slug}.html` }));

  const LEVELS = { B: "Basic", I: "Intermediate", A: "Advanced" };
  const KEY = "rag-learning-path:learned";
  const THEME_KEY = "rag-learning-path:theme";
  const KNOWN_KEY = "rag-learning-path:known-questions";
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  const learned = new Set(store.get(KEY, []));
  try { const t = localStorage.getItem(THEME_KEY); if (t) document.documentElement.dataset.theme = t; } catch { /* ignore */ }

  const el = (tag, attrs = {}, html = "") => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (html) e.innerHTML = html;
    return e;
  };

  // ---------- Q&A data (assets/qa/NN.js, one file per lesson) ----------
  function loadIds(ids, done) {
    window.QA = window.QA || {};
    let left = ids.length;
    if (!left) return done();
    ids.forEach((id) => {
      const s = document.createElement("script");
      s.src = `assets/qa/${id}.js`;
      s.onload = s.onerror = () => { if (--left === 0) done(); };
      document.head.appendChild(s);
    });
  }
  const loadStages = (stages, done) => loadIds(LESSONS.filter((l) => stages.includes(l.stage)).map((l) => l.id), done);

  function qaHtml(item, opts = {}) {
    const lv = item.l || "B";
    return `<details class="qa" data-level="${lv}"${opts.open ? " open" : ""}>
      <summary><span class="lv lv-${lv}">${LEVELS[lv]}</span><span class="qq">${item.q}</span>${opts.lessonTag || ""}</summary>
      <div class="ans">
        <span class="lbl">Model answer</span>
        <div class="say">${item.a}</div>
        ${item.k && item.k.length ? `<div class="kw"><b>Key words to say:</b> ${item.k.map((k) => `<span>${k}</span>`).join("")}</div>` : ""}
        ${item.f ? `<div class="fu"><b>Likely follow-up:</b> ${item.f}</div>` : ""}
      </div></details>`;
  }

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
      <a class="tlink" href="interview-questions.html">Interview Q&amp;A</a>
      <a class="tlink" href="revision.html">Revision</a>
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
    let stage = 0;
    let html = `<a class="item" href="index.html"><span class="n">⌂</span><span>Start here · the path</span></a>
      <a class="item" href="interview-questions.html"><span class="n">?</span><span>Interview Q&amp;A bank</span></a>
      <a class="item" href="revision.html"><span class="n">✎</span><span>Last-day revision</span></a>`;
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

  function mountShell(main, currentId, crumb) {
    const shell = el("div", { class: "shell" });
    main.replaceWith(shell);
    shell.append(sidebar(currentId), main);
    document.body.prepend(topbar(crumb));
    requestAnimationFrame(() => {
      const nav = document.querySelector(".sidebar"), item = nav && nav.querySelector("a.item.current");
      if (item) nav.scrollTop = item.offsetTop - nav.clientHeight / 2 + item.offsetHeight / 2;
    });
  }

  // ---------- lesson page ----------
  function lessonPage(id) {
    const i = LESSONS.findIndex((l) => l.id === id);
    const l = LESSONS[i], prev = LESSONS[i - 1], next = LESSONS[i + 1];
    const st = STAGES[l.stage];
    document.title = `${l.id} · ${l.title} — RAG Learning Path`;

    const main = document.querySelector("main");
    const article = main.querySelector("article");
    const hero = el("header", { class: "hero" });
    const prereq = prev ? `<a href="${prev.href}">${prev.id} · ${prev.title}</a>` : "nothing — start here";
    hero.innerHTML = `
      <span class="stage-chip" style="background:${st.color}">Stage ${l.stage} · ${st.name}</span>
      <h1>${l.id} · ${l.title}</h1>
      <p class="lead">${l.summary}</p>
      <div class="meta"><span><b>Lesson ${i + 1}</b> of ${LESSONS.length}</span><span>⏱ about <b>${l.minutes} min</b></span><span>Read first: ${prereq}</span><span><a href="#interview">Jump to interview questions ↓</a></span></div>`;
    article.prepend(hero);

    const qaHost = el("section", { class: "qa-host" });
    article.append(qaHost);

    const pager = el("nav", { class: "pager", "aria-label": "Previous and next lesson" });
    pager.innerHTML = `
      ${prev ? `<a class="prev" href="${prev.href}"><small>← Previous</small>${prev.id} · ${prev.title}</a>` : `<a class="prev" href="index.html"><small>← Back</small>The learning path</a>`}
      <button class="learned" type="button"></button>
      ${next ? `<a class="next" href="${next.href}"><small>Next →</small>${next.id} · ${next.title}</a>` : `<a class="next" href="interview-questions.html"><small>Finished →</small>Practice all interview questions</a>`}`;
    article.append(pager);
    const btn = pager.querySelector(".learned");
    const paint = () => { const on = learned.has(id); btn.classList.toggle("on", on); btn.textContent = on ? "✓ Learned" : "Mark as learned"; };
    btn.addEventListener("click", () => {
      learned.has(id) ? learned.delete(id) : learned.add(id);
      store.set(KEY, [...learned]); paint();
      document.querySelector(".topbar .prog").innerHTML = progressHtml();
      const item = document.querySelector(".sidebar a.item.current");
      if (item) { item.querySelector(".done")?.remove(); if (learned.has(id)) item.insertAdjacentHTML("beforeend", '<span class="done">✓</span>'); }
    });
    paint();

    mountShell(main, id, `Stage ${l.stage} · ${st.name} › ${l.title}`);

    loadIds([id], () => {
      const d = (window.QA || {})[id];
      if (!d) return;
      const defBox = article.querySelector(".oneline[data-def]");
      if (defBox && d.def) defBox.insertAdjacentHTML("beforeend", d.def);
      const n = article.querySelectorAll("h2 .ix").length;
      const counts = { B: 0, I: 0, A: 0 };
      d.qa.forEach((q) => counts[q.l || "B"]++);
      qaHost.innerHTML = `
        <h2 id="interview"><span class="ix">${n + 1}</span>Interview questions and answers</h2>
        <p class="note-line">${d.qa.length} questions with model answers · <span class="lv lv-B">Basic</span> ${counts.B} · <span class="lv lv-I">Intermediate</span> ${counts.I} · <span class="lv lv-A">Advanced</span> ${counts.A}. Read each answer, then use practice mode to hide the answers and say them out loud.</p>
        <div class="qa-tools"><button type="button" data-act="close">Practice mode: hide answers</button><button type="button" data-act="open">Show all answers</button></div>
        ${d.qa.map((q) => qaHtml(q, { open: true })).join("")}
        <h2 id="revise"><span class="ix">${n + 2}</span>Quick revision</h2>
        <div class="revise-card"><div class="one"><b>Definition:</b> ${d.def || d.oneLine}</div><ul>${d.revise.map((r) => `<li>${r}</li>`).join("")}</ul></div>`;
      qaHost.querySelector(".qa-tools").addEventListener("click", (e) => {
        const act = e.target.dataset.act;
        if (!act) return;
        qaHost.classList.toggle("practice", act === "close");
        qaHost.querySelectorAll("details.qa").forEach((x) => { x.open = act === "open"; });
      });
      if (location.hash === "#interview" || location.hash === "#revise") document.querySelector(location.hash)?.scrollIntoView();
    });

    addEventListener("keydown", (e) => {
      if (/input|textarea|select/i.test(e.target.tagName)) return;
      if (e.key === "ArrowLeft" && prev) location.href = prev.href;
      if (e.key === "ArrowRight" && next) location.href = next.href;
    });
  }

  // ---------- index page ----------
  function indexPage() {
    const host = document.getElementById("path");
    const nextUp = LESSONS.find((l) => !learned.has(l.id)) || LESSONS[0];
    const cont = document.getElementById("continue");
    if (cont) { cont.href = nextUp.href; cont.textContent = learned.size ? `Continue: ${nextUp.id} · ${nextUp.title}` : `Start: 01 · ${LESSONS[0].title}`; }
    const total = LESSONS.reduce((a, l) => a + l.minutes, 0);
    const tm = document.getElementById("total-time");
    if (tm) tm.textContent = `${LESSONS.length} lessons · about ${Math.round(total / 60)} hours`;
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
    document.body.prepend(topbar("Start here — learn in this order"));
    document.querySelector(".menu-btn").style.display = "none";
    loadStages([1, 2, 3, 4, 5], () => {
      const total = Object.values(window.QA || {}).reduce((a, d) => a + d.qa.length, 0);
      document.querySelectorAll(".q-count").forEach((x) => { x.textContent = total; });
    });
  }

  // ---------- interview question bank ----------
  function bankPage() {
    document.body.prepend(topbar("Interview Q&A bank — every question, with model answers"));
    document.querySelector(".menu-btn").style.display = "none";
    const known = new Set(store.get(KNOWN_KEY, []));
    loadStages([1, 2, 3, 4, 5], () => {
      const all = [];
      for (const l of LESSONS) ((window.QA || {})[l.id]?.qa || []).forEach((q, j) => all.push({ ...q, lesson: l, key: `${l.id}-${j}` }));
      const stageSel = document.getElementById("f-stage"), search = document.getElementById("f-search");
      const levelBoxes = [...document.querySelectorAll(".f-level")];
      const onlyNew = document.getElementById("f-new");
      const list = document.getElementById("bank-list"), count = document.getElementById("bank-count");
      const toggle = document.getElementById("toggle-answers");
      let openAll = false;
      stageSel.innerHTML = `<option value="">All stages</option>` + Object.entries(STAGES).map(([n, s]) => `<option value="${n}">Stage ${n} · ${s.name}</option>`).join("");

      const filtered = () => {
        const st = stageSel.value, txt = search.value.trim().toLowerCase();
        const lv = new Set(levelBoxes.filter((b) => b.checked).map((b) => b.value));
        return all.filter((q) => (!st || q.lesson.stage === +st) && lv.has(q.l || "B") && (!onlyNew.checked || !known.has(q.key)) &&
          (!txt || (q.q + " " + q.a + " " + (q.k || []).join(" ")).toLowerCase().includes(txt)));
      };
      function renderList() {
        const qs = filtered();
        count.textContent = `${qs.length} of ${all.length} questions shown · ${known.size} marked as known`;
        let html = "", cur = "";
        for (const q of qs) {
          if (q.lesson.id !== cur) { cur = q.lesson.id; html += `<h3 class="bank-h"><a href="${q.lesson.href}">${q.lesson.id} · ${q.lesson.title}</a></h3>`; }
          html += qaHtml(q, { open: openAll, lessonTag: `<button type="button" class="known${known.has(q.key) ? " on" : ""}" data-key="${q.key}">${known.has(q.key) ? "✓ known" : "mark known"}</button>` });
        }
        list.innerHTML = html || `<p>No questions match these filters.</p>`;
      }
      list.addEventListener("click", (e) => {
        const b = e.target.closest("button.known");
        if (!b) return;
        e.preventDefault();
        known.has(b.dataset.key) ? known.delete(b.dataset.key) : known.add(b.dataset.key);
        store.set(KNOWN_KEY, [...known]);
        renderList();
      });
      if (toggle) toggle.addEventListener("click", () => {
        openAll = !openAll;
        toggle.textContent = openAll ? "Hide all answers" : "Show all answers";
        renderList();
      });
      [stageSel, search, onlyNew, ...levelBoxes].forEach((x) => x.addEventListener("input", renderList));
      renderList();

      // flashcard practice
      const card = document.getElementById("flash"), fq = document.getElementById("fq"), fa = document.getElementById("fa"), fm = document.getElementById("fmeta");
      let deck = [], pos = 0;
      function showCard() {
        if (!deck.length) { fq.innerHTML = "No questions match the filters."; fa.innerHTML = ""; fm.textContent = ""; return; }
        const q = deck[pos];
        fm.innerHTML = `Card ${pos + 1} of ${deck.length} · <span class="lv lv-${q.l || "B"}">${LEVELS[q.l || "B"]}</span> · <a href="${q.lesson.href}">${q.lesson.id} · ${q.lesson.title}</a>`;
        fq.innerHTML = q.q;
        fa.innerHTML = `<div class="say">${q.a}</div>${q.k ? `<div class="kw"><b>Key words to say:</b> ${q.k.map((k) => `<span>${k}</span>`).join("")}</div>` : ""}`;
        fa.hidden = true;
      }
      document.getElementById("start-flash").addEventListener("click", () => {
        deck = filtered().sort(() => Math.random() - 0.5); pos = 0;
        card.hidden = false; showCard(); card.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      card.addEventListener("click", (e) => {
        const act = e.target.dataset && e.target.dataset.act;
        if (!act) return;
        if (act === "close") { card.hidden = true; return; }
        if (!deck.length) return;
        if (act === "show") fa.hidden = false;
        if (act === "knew") { known.add(deck[pos].key); store.set(KNOWN_KEY, [...known]); }
        if (act === "knew" || act === "again") { pos = (pos + 1) % deck.length; showCard(); renderList(); }
      });
    });
  }

  // ---------- revision sheet ----------
  function revisionPage() {
    document.body.prepend(topbar("Last-day revision — every lesson on one page"));
    document.querySelector(".menu-btn").style.display = "none";
    const host = document.getElementById("rev");
    loadStages([1, 2, 3, 4, 5], () => {
      for (const [n, st] of Object.entries(STAGES)) {
        const block = el("section", { class: "stage-block" });
        block.innerHTML = `<h2 style="color:${st.color}">Stage ${n} · ${st.name}</h2>` + LESSONS.filter((l) => l.stage === +n).map((l) => {
          const d = (window.QA || {})[l.id];
          return `<div class="rev-item"><h3><a href="${l.href}">${l.id} · ${l.title}</a></h3>${d ? `<div class="one">${d.def || d.oneLine}</div><ul>${d.revise.map((r) => `<li>${r}</li>`).join("")}</ul>` : ""}</div>`;
        }).join("");
        host.append(block);
      }
    });
  }

  window.RAG_PATH = { LESSONS, STAGES, LEVELS };
  document.addEventListener("DOMContentLoaded", () => {
    const id = document.body.dataset.lesson, page = document.body.dataset.page;
    if (id) lessonPage(id);
    else if (page === "index") indexPage();
    else if (page === "bank") bankPage();
    else if (page === "revision") revisionPage();
  });
})();
