/* Fake News BERT Audit — UI behaviour (no dependencies) */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  /* ---------- Scroll reveal (content stays visible without JS) ---------- */
  function initReveal() {
    var items = $$("[data-reveal]");
    if (!items.length || reduceMotion || !("IntersectionObserver" in window)) return;
    root.classList.add("js-reveal");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    items.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Toasts ---------- */
  function dismissToast(t) {
    if (!t || t.classList.contains("leaving")) return;
    t.classList.add("leaving");
    setTimeout(function () { t.remove(); }, 260);
  }
  function initToasts() {
    $$(".toast").forEach(function (t, i) {
      var btn = $("button", t);
      if (btn) btn.addEventListener("click", function () { dismissToast(t); });
      var ms = t.dataset.level === "error" ? 8000 : 5000;
      setTimeout(function () { dismissToast(t); }, ms + i * 400);
    });
  }
  window.showToast = function (text, level) {
    var box = $(".toasts");
    if (!box) return;
    var icons = { success: "✓", error: "!", warning: "!", info: "i" };
    var t = document.createElement("div");
    t.className = "toast";
    t.dataset.level = level || "info";
    t.setAttribute("role", level === "error" ? "alert" : "status");
    t.innerHTML = '<span class="toast-icon" aria-hidden="true"></span><span></span><button type="button" aria-label="Dismiss">×</button>';
    t.firstChild.textContent = icons[t.dataset.level] || "i";
    t.children[1].textContent = text;
    t.lastChild.addEventListener("click", function () { dismissToast(t); });
    box.appendChild(t);
    setTimeout(function () { dismissToast(t); }, 4000);
  };

  /* ---------- Mobile menu ---------- */
  function initMenu() {
    $$("[data-menu-toggle]").forEach(function (btn) {
      var bar = btn.closest(".topbar");
      btn.addEventListener("click", function () {
        var open = bar.classList.toggle("open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && bar.classList.contains("open")) {
          bar.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); btn.focus();
        }
      });
    });
  }

  /* ---------- Password visibility ---------- */
  function initPasswordToggles() {
    $$("[data-pw-toggle]").forEach(function (btn) {
      var input = btn.parentElement.querySelector("input");
      btn.addEventListener("click", function () {
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
        btn.setAttribute("aria-pressed", show ? "true" : "false");
      });
    });
  }

  /* ---------- Confirm dialog for destructive forms ---------- */
  function initConfirm() {
    var dialog = $("#confirm-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return;
    var pending = null;
    $$("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (form.dataset.confirmed) return;
        e.preventDefault();
        pending = form;
        $("[data-confirm-title]", dialog).textContent = form.dataset.confirmTitle || "Are you sure?";
        $("[data-confirm-text]", dialog).textContent = form.dataset.confirm;
        $("[data-confirm-ok]", dialog).textContent = form.dataset.confirmOk || "Confirm";
        dialog.showModal();
      });
    });
    $("[data-confirm-ok]", dialog).addEventListener("click", function () {
      dialog.close();
      if (pending) { pending.dataset.confirmed = "1"; pending.requestSubmit ? pending.requestSubmit() : pending.submit(); }
    });
    $("[data-confirm-cancel]", dialog).addEventListener("click", function () { dialog.close(); pending = null; });
  }

  /* ---------- Numbers, gauges, bars ---------- */
  function countUp(el) {
    var target = parseFloat(el.dataset.count);
    var decimals = parseInt(el.dataset.decimals || "0", 10);
    if (isNaN(target)) return;
    if (reduceMotion) { el.textContent = target.toFixed(decimals); return; }
    var start = null, dur = 900;
    function frame(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * eased).toFixed(decimals);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function setGauge(el, value) {
    var fill = $(".g-fill", el);
    if (!fill) return;
    var c = 2 * Math.PI * parseFloat(fill.getAttribute("r"));
    var target = (c * Math.max(0, Math.min(100, value)) / 100).toFixed(2) + " 400";
    if (reduceMotion) { fill.style.strokeDasharray = target; return; }
    fill.style.strokeDasharray = "0 400";
    requestAnimationFrame(function () { requestAnimationFrame(function () { fill.style.strokeDasharray = target; }); });
  }
  function setBars(ctx) {
    $$(".prob-fill, .split span", ctx).forEach(function (bar) {
      var w = bar.dataset.w;
      if (w === undefined) return;
      bar.style.width = "0%";
      requestAnimationFrame(function () { requestAnimationFrame(function () { bar.style.width = w + "%"; }); });
    });
  }
  function initMetrics() {
    $$("[data-count]").forEach(countUp);
    $$("[data-gauge]").forEach(function (g) { setGauge(g, parseFloat(g.dataset.gauge)); });
    setBars(document);
  }

  /* ---------- Copy to clipboard ---------- */
  function initCopy() {
    $$("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var src = btn.dataset.copy.charAt(0) === "#" ? $(btn.dataset.copy) : null;
        var text = src ? (src.value || src.textContent).trim() : btn.dataset.copy;
        var done = function () {
          var label = $("[data-copy-label]", btn) || btn;
          var prev = label.textContent;
          label.textContent = "Copied";
          btn.classList.add("btn-success");
          setTimeout(function () { label.textContent = prev; btn.classList.remove("btn-success"); }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { window.showToast("Copy failed — select the text manually.", "error"); });
        } else { window.showToast("Copy isn't available in this browser.", "error"); }
      });
    });
  }

  /* ---------- Expand / collapse long text ---------- */
  function initClamp() {
    $$("[data-clamp]").forEach(function (el) {
      var btn = $("[data-clamp-toggle='" + el.id + "']");
      if (!btn) return;
      if (el.scrollHeight <= 300) { el.classList.remove("clamped"); btn.hidden = true; return; }
      btn.addEventListener("click", function () {
        var clamped = el.classList.toggle("clamped");
        btn.textContent = clamped ? "Show full text" : "Collapse";
        btn.setAttribute("aria-expanded", clamped ? "false" : "true");
      });
    });
  }

  /* ---------- Table filter (admin) ---------- */
  function initTableFilter() {
    $$("[data-filter-table]").forEach(function (input) {
      var table = $(input.dataset.filterTable);
      var empty = $(input.dataset.filterEmpty || "#__none");
      input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase(), shown = 0;
        $$("tbody tr", table).forEach(function (tr) {
          var hit = tr.textContent.toLowerCase().indexOf(q) !== -1;
          tr.hidden = !hit; if (hit) shown++;
        });
        if (empty) empty.hidden = shown !== 0;
      });
    });
  }

  /* ---------- Analyzer (detect page) ---------- */
  var MAX_TOKENS = 512;
  function estimateTokens(text) {
    // WordPiece splits roughly 1.3 tokens per English word, plus [CLS] and [SEP]
    var words = text.trim() ? text.trim().split(/\s+/).length : 0;
    return words ? Math.round(words * 1.3) + 2 : 0;
  }
  function initAnalyzer() {
    var form = $("#analyze-form");
    if (!form) return;
    var ta = $("#news_text", form);
    var words = $("[data-words]"), chars = $("[data-chars]"), tokens = $("[data-tokens]");
    var meter = $(".token-meter span"), over = $("[data-over]");
    var submit = $("[type=submit]", form);

    function update() {
      var text = ta.value;
      var w = text.trim() ? text.trim().split(/\s+/).length : 0;
      var t = estimateTokens(text);
      words.textContent = w.toLocaleString();
      chars.textContent = text.length.toLocaleString();
      tokens.textContent = "~" + t.toLocaleString();
      meter.style.width = Math.min(100, (t / MAX_TOKENS) * 100) + "%";
      meter.style.background = t > MAX_TOKENS ? "var(--warn)" : "var(--data)";
      tokens.parentElement.classList.toggle("over", t > MAX_TOKENS);
      if (over) over.hidden = t <= MAX_TOKENS;
      submit.disabled = w === 0;
    }
    ta.addEventListener("input", update);
    update();

    $$("[data-sample]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        ta.value = $("#" + btn.dataset.sample).textContent.trim();
        update(); ta.focus();
      });
    });
    var clear = $("[data-clear]");
    if (clear) clear.addEventListener("click", function () { ta.value = ""; update(); ta.focus(); });

    ta.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.submit(); }
    });

    form.addEventListener("submit", function (e) {
      var w = ta.value.trim() ? ta.value.trim().split(/\s+/).length : 0;
      if (w < 5) {
        e.preventDefault();
        window.showToast("Add at least a full sentence — the model needs context to judge writing style.", "warning");
        ta.focus();
        return;
      }
      submit.setAttribute("aria-busy", "true");
      runProcessing(ta.value);
    });
  }

  /* Processing overlay: shows the pipeline stages while the server runs the model.
     Stages advance on a timer; the last stage completes when the result page loads. */
  function runProcessing(text) {
    var overlay = $("#processing");
    if (!overlay) return;
    var stream = $(".token-stream", overlay);
    var pieces = text.trim().split(/\s+/).slice(0, 36);
    stream.innerHTML = "";
    var mk = function (label, cls) { var s = document.createElement("span"); s.textContent = label; if (cls) s.className = cls; stream.appendChild(s); return s; };
    mk("[CLS]", "t-special");
    pieces.forEach(function (w) { mk(w.toLowerCase().replace(/[^\w'’-]/g, "").slice(0, 16) || w.slice(0, 4)); });
    if (text.trim().split(/\s+/).length > 36) mk("…");
    mk("[SEP]", "t-special");
    $("[data-token-estimate]", overlay).textContent = "~" + Math.min(estimateTokens(text), MAX_TOKENS) + " tokens";

    if (overlay.parentElement !== document.body) document.body.appendChild(overlay);  // escape page stacking contexts
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    var heading = $("#processing-title", overlay);
    if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus(); }

    var spans = $$("span", stream), i = 0;
    var lit = setInterval(function () {
      if (i < spans.length) { spans[i].classList.add("lit"); i++; } else { clearInterval(lit); }
    }, reduceMotion ? 0 : 35);

    var stages = $$(".stage", overlay);
    var timings = [0, 450, 1000, 1700, 2300];  // last stage (saving) waits for the server
    stages.forEach(function (st, idx) {
      setTimeout(function () {
        if (idx > 0) { stages[idx - 1].classList.remove("active"); stages[idx - 1].classList.add("done"); }
        st.classList.add("active");
      }, reduceMotion ? 0 : (timings[idx] !== undefined ? timings[idx] : timings[timings.length - 1] + 600));
    });
    var status = $("[data-processing-status]", overlay);
    setTimeout(function () { if (status) status.textContent = "Still working — the first analysis after a restart also loads the 110M-parameter model."; }, 6000);
  }
  // Hide the overlay again if the page is restored from the back/forward cache
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      var o = $("#processing"); if (o) o.hidden = true;
      document.body.style.overflow = "";
      $$("[aria-busy='true']").forEach(function (b) { b.removeAttribute("aria-busy"); });
    }
  });

  /* ---------- Landing: live preview from the real model ---------- */
  function initPreview() {
    var box = $("#preview");
    if (!box) return;
    var data = null, current = "wire";
    var tabs = $$("[role=tab]", box);
    var text = $("[data-p-text]", box), label = $("[data-p-label]", box), gauge = $("[data-p-gauge]", box);
    var gaugeVal = $("[data-p-conf]", box), meta = $("[data-p-meta]", box), note = $("[data-p-note]", box);
    var bars = { Real: $("[data-p-real]", box), Fake: $("[data-p-fake]", box) };

    function render() {
      var s = data.samples[current];
      var floor1 = function (x) { return Math.floor(x * 10) / 10; };  // never round up to 100.0%
      var real = s.real_probability * 100, conf = floor1(s.label === "Real" ? real : 100 - real);
      text.textContent = s.text;
      label.textContent = s.label;
      label.className = "badge " + (s.label === "Real" ? "badge-real" : "badge-fake");
      gauge.style.setProperty("--c", s.label === "Real" ? "var(--real)" : "var(--fake)");
      gaugeVal.textContent = conf.toFixed(1) + "%";
      setGauge(gauge, conf);
      bars.Real.querySelector(".prob-fill").dataset.w = floor1(real);
      bars.Real.querySelector(".prob-val").textContent = floor1(real).toFixed(1) + "%";
      bars.Fake.querySelector(".prob-fill").dataset.w = floor1(100 - real);
      bars.Fake.querySelector(".prob-val").textContent = floor1(100 - real).toFixed(1) + "%";
      setBars(box);
      meta.innerHTML = "";
      [["tokens", s.token_count + " / 512"], ["inference", s.latency_ms + " ms"], ["model", data.model]].forEach(function (m) {
        var span = document.createElement("span"); span.textContent = m[0] + " "; var b = document.createElement("b"); b.textContent = m[1]; span.appendChild(b); meta.appendChild(span);
      });
    }
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
        current = tab.dataset.sampleKey;
        if (data) render();
      });
    });
    fetch(box.dataset.src, { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (json) {
        data = json;
        $$(".skeleton", box).forEach(function (s) { s.hidden = true; });
        $$("[data-p-live]", box).forEach(function (s) { s.hidden = false; });
        note.innerHTML = '<span class="live-dot" aria-hidden="true"></span> Live output — the model on this server just analyzed this sample.';
        render();
      })
      .catch(function () {
        note.textContent = "Preview unavailable — the model isn't loaded on this server. Run python download_model.py.";
        $$(".skeleton", box).forEach(function (s) { s.classList.remove("skeleton"); });
      });
  }

  /* ---------- Landing: hero token network (canvas, pauses off-screen) ---------- */
  function initHeroCanvas() {
    var canvas = $(".hero-canvas");
    if (!canvas || reduceMotion) return;
    var ctx = canvas.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var nodes = [], w = 0, h = 0, running = false, raf = 0;

    function resize() {
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var count = Math.max(18, Math.min(46, Math.round((w * h) / 26000)));
      nodes = [];
      for (var i = 0; i < count; i++) {
        nodes.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.18, vy: (Math.random() - 0.5) * 0.18, r: Math.random() * 1.6 + 0.8, hot: Math.random() < 0.12 });
      }
    }
    function tick() {
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < nodes.length; i++) {
        var a = nodes[i];
        a.x += a.vx; a.y += a.vy;
        if (a.x < 0 || a.x > w) a.vx *= -1;
        if (a.y < 0 || a.y > h) a.vy *= -1;
        for (var j = i + 1; j < nodes.length; j++) {
          var b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d = dx * dx + dy * dy;
          if (d < 19000) {
            ctx.strokeStyle = "rgba(142,162,255," + (0.16 * (1 - d / 19000)).toFixed(3) + ")";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
        ctx.fillStyle = a.hot ? "rgba(255,181,71,0.8)" : "rgba(167,177,198,0.5)";
        ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
      }
      if (running) raf = requestAnimationFrame(tick);
    }
    resize();
    window.addEventListener("resize", function () { resize(); });
    new IntersectionObserver(function (entries) {
      running = entries[0].isIntersecting && !document.hidden;
      cancelAnimationFrame(raf);
      if (running) raf = requestAnimationFrame(tick);
    }).observe(canvas);
    document.addEventListener("visibilitychange", function () {
      running = !document.hidden;
      cancelAnimationFrame(raf);
      if (running) raf = requestAnimationFrame(tick);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initReveal(); initToasts(); initMenu(); initPasswordToggles(); initConfirm();
    initMetrics(); initCopy(); initClamp(); initTableFilter(); initAnalyzer(); initPreview(); initHeroCanvas();
  });
})();
