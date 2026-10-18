// Tiny orthogonal-connector helper shared by the HTML diagrams.
// Each diagram calls drawEdges([...]) after layout; render.py waits for window.__ready.
(function () {
  const NS = "http://www.w3.org/2000/svg";

  function canvasBox() {
    return document.getElementById("canvas").getBoundingClientRect();
  }

  function box(id) {
    const el = document.getElementById(id);
    if (!el) throw new Error("missing element #" + id);
    const r = el.getBoundingClientRect();
    const c = canvasBox();
    return { l: r.left - c.left, t: r.top - c.top, r: r.right - c.left, b: r.bottom - c.top, w: r.width, h: r.height };
  }

  function anchor([id, side, f = 0.5]) {
    const b = box(id);
    if (side === "top") return [b.l + b.w * f, b.t];
    if (side === "bottom") return [b.l + b.w * f, b.b];
    if (side === "left") return [b.l, b.t + b.h * f];
    return [b.r, b.t + b.h * f];
  }

  // Resolve a channel coordinate: a number, or [id, side, offset].
  function coord(v, axis) {
    if (typeof v === "number") return v;
    const [id, side, off = 0] = v;
    const b = box(id);
    const base = { top: b.t, bottom: b.b, left: b.l, right: b.r, cx: b.l + b.w / 2, cy: b.t + b.h / 2 }[side];
    return base + off;
  }

  function route(e) {
    const p0 = anchor(e.from), p1 = anchor(e.to);
    const s0 = e.from[1], s1 = e.to[1];
    const vert = (s) => s === "top" || s === "bottom";
    // align: start the edge straight above/beside its target instead of at the given fraction
    if (e.align === "to") { if (vert(s1)) p1[0] = p0[0]; else p1[1] = p0[1]; }
    else if (e.align) { if (vert(s0)) p0[0] = p1[0]; else p0[1] = p1[1]; }
    // fromX / toX: pin the x coordinate of a top/bottom anchor to another element
    if (e.fromX) p0[0] = coord(e.fromX);
    if (e.toX) p1[0] = coord(e.toX);
    if (e.points) return [p0, ...e.points.map(([x, y]) => [coord(x), coord(y)]), p1];
    if (vert(s0) && vert(s1)) {
      if (Math.abs(p0[0] - p1[0]) < 0.5) return [p0, p1];
      const y = e.y !== undefined ? coord(e.y) : (p0[1] + p1[1]) / 2;
      return [p0, [p0[0], y], [p1[0], y], p1];
    }
    if (!vert(s0) && !vert(s1)) {
      if (Math.abs(p0[1] - p1[1]) < 0.5) return [p0, p1];
      const x = e.x !== undefined ? coord(e.x) : (p0[0] + p1[0]) / 2;
      return [p0, [x, p0[1]], [x, p1[1]], p1];
    }
    if (vert(s0)) return [p0, [p0[0], p1[1]], p1];
    return [p0, [p1[0], p0[1]], p1];
  }

  function pathD(pts, rad = 12) {
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const d1 = Math.hypot(x1 - x0, y1 - y0), d2 = Math.hypot(x2 - x1, y2 - y1);
      if (d1 < 0.5 || d2 < 0.5) continue;
      const r = Math.min(rad, d1 / 2, d2 / 2);
      const ax = x1 + ((x0 - x1) / d1) * r, ay = y1 + ((y0 - y1) / d1) * r;
      const bx = x1 + ((x2 - x1) / d2) * r, by = y1 + ((y2 - y1) / d2) * r;
      d += ` L${ax},${ay} Q${x1},${y1} ${bx},${by}`;
    }
    const last = pts[pts.length - 1];
    return d + ` L${last[0]},${last[1]}`;
  }

  function marker(defs, color, id) {
    const m = document.createElementNS(NS, "marker");
    m.setAttribute("id", id);
    m.setAttribute("viewBox", "0 0 10 10");
    m.setAttribute("refX", "9");
    m.setAttribute("refY", "5");
    m.setAttribute("markerWidth", "9");
    m.setAttribute("markerHeight", "9");
    m.setAttribute("markerUnits", "userSpaceOnUse");
    m.setAttribute("orient", "auto-start-reverse");
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", "M0,0 L10,5 L0,10 z");
    p.setAttribute("fill", color);
    m.appendChild(p);
    defs.appendChild(m);
  }

  window.drawEdges = function (edges) {
    const c = canvasBox();
    const svg = document.getElementById("edges");
    svg.setAttribute("width", c.width);
    svg.setAttribute("height", c.height);
    svg.setAttribute("viewBox", `0 0 ${c.width} ${c.height}`);
    const defs = document.createElementNS(NS, "defs");
    svg.appendChild(defs);
    const markers = {};
    const labels = [];

    for (const e of edges) {
      const color = e.color || "#64748b";
      const mid = "m" + color.replace(/[^0-9a-z]/gi, "");
      if (!markers[mid]) { marker(defs, color, mid); markers[mid] = true; }
      const pts = route(e);
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", pathD(pts, e.radius ?? 12));
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", color);
      path.setAttribute("stroke-width", e.width || 2);
      path.setAttribute("stroke-linecap", "round");
      if (e.dash) path.setAttribute("stroke-dasharray", e.dash === true ? "7 6" : e.dash);
      if (e.head !== false) path.setAttribute("marker-end", `url(#${mid})`);
      if (e.both) path.setAttribute("marker-start", `url(#${mid})`);
      svg.appendChild(path);

      if (e.label) {
        // default: centre of the longest segment
        let seg = e.seg;
        if (seg === undefined) {
          let best = -1;
          for (let i = 0; i < pts.length - 1; i++) {
            const len = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
            if (len > best) { best = len; seg = i; }
          }
        }
        if (seg < 0) seg = pts.length - 1 + seg;
        const t = e.t ?? 0.5;
        let x = pts[seg][0] + (pts[seg + 1][0] - pts[seg][0]) * t + (e.dx || 0);
        let y = pts[seg][1] + (pts[seg + 1][1] - pts[seg][1]) * t + (e.dy || 0);
        if (e.labelAt) { x = coord(e.labelAt[0]); y = coord(e.labelAt[1]); }
        labels.push({ x, y, text: e.label, color, rotate: e.rotate });
      }
    }

    const layer = document.getElementById("edge-labels");
    for (const l of labels) {
      const div = document.createElement("div");
      div.className = "edge-label";
      div.style.left = l.x + "px";
      div.style.top = l.y + "px";
      div.style.color = l.color;
      div.style.borderColor = l.color + "55";
      if (l.rotate) div.style.transform = "translate(-50%, -50%) rotate(-90deg)";
      div.innerHTML = l.text;
      layer.appendChild(div);
    }
  };

  window.whenLaidOut = function (fn) {
    const go = () => requestAnimationFrame(() => requestAnimationFrame(() => {
      fn();
      window.__ready = true;
      if (window.initViewer) window.initViewer(); // fit-to-window view in the browser (skipped for PNG export)
    }));
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(go); else window.addEventListener("load", go);
  };
})();
