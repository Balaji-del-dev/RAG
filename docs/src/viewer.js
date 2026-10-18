// Fit-to-window viewer for the diagram pages.
// Opens the diagram scaled to 100% of the browser width and height (no scrollbars);
// wheel = zoom at cursor · drag = pan · double-click = toggle fit / 100% · keys: 0 fit, 1 actual size, + / - zoom.
// render.py loads pages with ?export=1, which leaves the canvas at its natural size for the PNG screenshot.
(function () {
  const EXPORT = new URLSearchParams(location.search).has("export");

  window.initViewer = function () {
    if (EXPORT || window.__viewer) return;
    window.__viewer = true;
    const canvas = document.getElementById("canvas");
    const W = canvas.offsetWidth, H = canvas.offsetHeight;

    const root = document.documentElement;
    root.style.overflow = "hidden";
    Object.assign(document.body.style, { margin: "0", overflow: "hidden", width: "100vw", height: "100vh", position: "relative" });
    // No permanent `will-change: transform`: it makes Chrome keep the text rasterised at the first scale
    // and stretch that bitmap when zooming in (blurry at 150%+). It is only switched on while the user is
    // actively zooming/panning (smooth), then removed so the browser repaints crisp text at the new scale.
    Object.assign(canvas.style, { position: "absolute", left: "0", top: "0", transformOrigin: "0 0" });
    document.body.style.textRendering = "geometricPrecision";

    let s = 1, tx = 0, ty = 0, fitted = true;
    const fitScale = () => Math.min((innerWidth - 16) / W, (innerHeight - 16) / H);

    const bar = document.createElement("div");
    bar.innerHTML =
      '<button data-a="fit" title="Fit to window (0)">Fit</button>' +
      '<button data-a="one" title="Actual size (1)">100%</button>' +
      '<button data-a="out" title="Zoom out (-)">−</button>' +
      '<span class="z"></span>' +
      '<button data-a="in" title="Zoom in (+)">+</button>' +
      '<span class="hint">scroll to zoom · drag to pan · double-click to toggle</span>';
    Object.assign(bar.style, {
      position: "fixed", right: "14px", bottom: "14px", zIndex: 10, display: "flex", alignItems: "center", gap: "6px",
      padding: "6px 8px", borderRadius: "12px", background: "rgba(15,23,42,.86)", color: "#e2e8f0",
      font: "600 13px 'Noto Sans', 'Liberation Sans', sans-serif", boxShadow: "0 4px 18px rgba(15,23,42,.25)", userSelect: "none",
    });
    const style = document.createElement("style");
    style.textContent =
      ".viewer-bar button{font:inherit;color:#fff;background:#334155;border:0;border-radius:8px;padding:5px 10px;cursor:pointer}" +
      ".viewer-bar button:hover{background:#475569}.viewer-bar .z{min-width:52px;text-align:center}" +
      ".viewer-bar .hint{color:#94a3b8;font-weight:500;margin-left:6px}" +
      "@media (max-width:900px){.viewer-bar .hint{display:none}}";
    document.head.appendChild(style);
    bar.className = "viewer-bar";
    document.body.appendChild(bar);
    const zoomLabel = bar.querySelector(".z");

    let settleTimer = null;
    function apply(moving = false) {
      if (moving) {
        canvas.style.willChange = "transform";
        clearTimeout(settleTimer);
        settleTimer = setTimeout(settle, 140);
      }
      canvas.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
      zoomLabel.textContent = Math.round(s * 100) + "%";
    }
    function settle() {
      // whole-pixel offset + no compositing hint => the browser repaints text and lines sharp at this zoom
      tx = Math.round(tx);
      ty = Math.round(ty);
      canvas.style.willChange = "auto";
      apply();
    }
    function fit() {
      s = fitScale();
      tx = Math.round((innerWidth - W * s) / 2);
      ty = Math.round((innerHeight - H * s) / 2);
      fitted = true;
      settle();
    }
    function zoomAt(newS, mx, my, moving = true) {
      newS = Math.max(fitScale() * 0.5, Math.min(4, newS));
      tx = mx - (mx - tx) * (newS / s);
      ty = my - (my - ty) * (newS / s);
      s = newS;
      fitted = false;
      if (moving) apply(true); else settle();
    }

    addEventListener("wheel", (e) => {
      if (e.target.closest && e.target.closest(".viewer-bar")) return;
      e.preventDefault();
      zoomAt(s * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
    }, { passive: false });

    let drag = null;
    addEventListener("pointerdown", (e) => {
      if (e.target.closest(".viewer-bar")) return;
      drag = { x: e.clientX, y: e.clientY };
      document.body.style.cursor = "grabbing";
    });
    addEventListener("pointermove", (e) => {
      if (!drag) return;
      tx += e.clientX - drag.x;
      ty += e.clientY - drag.y;
      drag = { x: e.clientX, y: e.clientY };
      fitted = false;
      apply(true);
    });
    addEventListener("pointerup", () => { drag = null; document.body.style.cursor = ""; });

    addEventListener("dblclick", (e) => {
      if (e.target.closest(".viewer-bar")) return;
      if (fitted) zoomAt(1, e.clientX, e.clientY, false); else fit();
    });
    addEventListener("keydown", (e) => {
      const cx = innerWidth / 2, cy = innerHeight / 2;
      if (e.key === "0") fit();
      else if (e.key === "1") zoomAt(1, cx, cy, false);
      else if (e.key === "+" || e.key === "=") zoomAt(s * 1.25, cx, cy, false);
      else if (e.key === "-") zoomAt(s / 1.25, cx, cy, false);
    });
    bar.addEventListener("click", (e) => {
      const a = e.target.dataset && e.target.dataset.a;
      const cx = innerWidth / 2, cy = innerHeight / 2;
      if (a === "fit") fit();
      else if (a === "one") zoomAt(1, cx, cy, false);
      else if (a === "in") zoomAt(s * 1.25, cx, cy, false);
      else if (a === "out") zoomAt(s / 1.25, cx, cy, false);
    });
    addEventListener("resize", () => { if (fitted) fit(); });

    fit();
  };
})();
