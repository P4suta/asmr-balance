// Three pieces of progressive enhancement glue:
//   1. Tab switching (Inspect ↔ Scan).
//   2. Drag-and-drop on the inspect drop-zone.
//   3. Scan form submission + SSE consumer (per-file rows + live charts).
//
// Without JS the inspect form still works (HTMX); the scan form posts to
// /api/scan but cannot render live progress.

(() => {
  "use strict";

  // ---- palette (read live from CSS variables so charts follow theme) -
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const livePalette = () => ({
    ok: css("--ok"),
    warn: css("--warn"),
    fail: css("--fail"),
    neutral: css("--accent"),
    fg: css("--fg"),
    border: css("--zone-grid"),
  });
  let PALETTE = livePalette();
  const PLOTLY_OPTS = { responsive: true, displayModeBar: false };
  // Single source of truth for verdict copy (mirrors Jinja2 ``verdict_label``).
  const VERDICT_LABELS = { OK: "問題なし", WARN: "注意", FAIL: "要確認" };
  const verdictLabel = (name) => VERDICT_LABELS[name] || name;

  // ---- theme toggle (light / dark / system) -------------------------
  const THEMES = ["system", "light", "dark"];
  const THEME_ICONS = { system: "🖥", light: "☀", dark: "🌙" };
  const THEME_STORAGE = "asmr-balance-theme";
  const themeBtn = document.getElementById("theme-toggle");
  const applyTheme = (t) => {
    document.documentElement.dataset.theme = t;
    if (themeBtn) themeBtn.textContent = THEME_ICONS[t] || THEME_ICONS.system;
    PALETTE = livePalette();
  };
  applyTheme(localStorage.getItem(THEME_STORAGE) || "system");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const current = document.documentElement.dataset.theme || "system";
      const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
      localStorage.setItem(THEME_STORAGE, next);
      applyTheme(next);
    });
  }
  // Follow OS theme changes in real-time when in "system" mode.
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
    if ((document.documentElement.dataset.theme || "system") === "system") {
      PALETTE = livePalette();
    }
  });

  // ---- tabs ----------------------------------------------------------
  const tabs = document.querySelectorAll("[data-tab]");
  const panes = document.querySelectorAll(".pane");
  const activateTab = (key) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === key;
      tab.classList.toggle("tab--active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panes.forEach((pane) => {
      const active = pane.id === `${key}-pane`;
      pane.classList.toggle("pane--active", active);
      pane.toggleAttribute("hidden", !active);
    });
  };
  tabs.forEach((tab) =>
    tab.addEventListener("click", () => activateTab(tab.dataset.tab)),
  );

  // ---- inspect form: drop zone state machine + elapsed tick ---------
  // States: empty → ready (file picked) → analyzing → done.
  // CSS handles visibility via [data-state]; JS only flips the attribute
  // and fills in dynamic copy (filename / size / elapsed).
  const inspectForm = document.getElementById("inspect-form");
  const inspectInput = document.getElementById("file-input");
  const inspectDrop = inspectForm && inspectForm.querySelector(".drop-zone");
  const inspectResultArea = document.getElementById("inspect-result-area");

  const formatBytes = (n) => {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  };

  const fillFileMeta = (selector, file) => {
    if (!inspectForm) return;
    const target = inspectForm.querySelector(selector);
    if (!target) return;
    target.querySelectorAll(".drop-zone__file-name").forEach((el) => {
      el.textContent = file.name;
    });
    target.querySelectorAll(".drop-zone__file-detail").forEach((el) => {
      el.textContent = formatBytes(file.size);
    });
  };

  const setState = (state) => {
    if (!inspectForm) return;
    inspectForm.dataset.state = state;
  };

  const resetInspect = () => {
    if (!inspectForm || !inspectInput) return;
    inspectInput.value = "";
    setState("empty");
    if (inspectResultArea) inspectResultArea.innerHTML = "";
    stopInspectTick();
  };

  if (inspectForm && inspectInput && inspectDrop) {
    // File picker change (manual click or after drop).
    inspectInput.addEventListener("change", () => {
      const file = inspectInput.files && inspectInput.files[0];
      if (!file) {
        setState("empty");
        return;
      }
      fillFileMeta(".drop-zone__file", file);
      setState("ready");
    });

    // Drag-and-drop handling.
    const stop = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    ["dragenter", "dragover"].forEach((evt) =>
      inspectDrop.addEventListener(evt, (e) => {
        stop(e);
        if (inspectForm.dataset.state === "empty" || inspectForm.dataset.state === "ready") {
          inspectDrop.classList.add("dragover");
        }
      }),
    );
    ["dragleave", "drop"].forEach((evt) =>
      inspectDrop.addEventListener(evt, (e) => {
        stop(e);
        inspectDrop.classList.remove("dragover");
      }),
    );
    inspectDrop.addEventListener("drop", (e) => {
      const files = e.dataTransfer && e.dataTransfer.files;
      if (!files || files.length === 0) return;
      // Block drop during analysis to avoid race.
      if (inspectForm.dataset.state === "analyzing") return;
      inspectInput.files = files;
      inspectInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    // Reset buttons (any data-action="reset" inside the drop zone).
    inspectForm.addEventListener("click", (e) => {
      const target = e.target.closest('[data-action="reset"]');
      if (!target) return;
      e.preventDefault();
      e.stopPropagation();
      resetInspect();
    });
  }

  // Elapsed-time tick on the analyzing state (HTMX-driven).
  let inspectTickHandle = null;
  let inspectStartedAt = 0;
  const stopInspectTick = () => {
    if (inspectTickHandle !== null) {
      clearInterval(inspectTickHandle);
      inspectTickHandle = null;
    }
  };
  const setElapsedText = (text) => {
    if (!inspectForm) return;
    inspectForm.querySelectorAll(".drop-zone__elapsed").forEach((el) => {
      el.textContent = text;
    });
  };
  const tickInspect = () => {
    setElapsedText(`${((performance.now() - inspectStartedAt) / 1000).toFixed(1)}s`);
  };
  document.body.addEventListener("htmx:beforeRequest", (e) => {
    if (e.detail.elt === inspectForm) {
      // Snapshot the file into the analyzing state.
      const file = inspectInput && inspectInput.files && inspectInput.files[0];
      if (file) {
        fillFileMeta(".drop-zone__progress", file);
        fillFileMeta(".drop-zone__done", file);
      }
      inspectStartedAt = performance.now();
      tickInspect();
      inspectTickHandle = setInterval(tickInspect, 100);
      setState("analyzing");
    }
  });
  document.body.addEventListener("htmx:afterRequest", (e) => {
    if (e.detail.elt === inspectForm) {
      stopInspectTick();
      const elapsed = ((performance.now() - inspectStartedAt) / 1000).toFixed(2);
      if (e.detail.successful) {
        // Show total elapsed alongside the filename in the done card.
        const file = inspectInput && inspectInput.files && inspectInput.files[0];
        if (inspectForm) {
          const doneCard = inspectForm.querySelector(".drop-zone__done");
          if (doneCard && file) {
            const detail = doneCard.querySelector(".drop-zone__file-detail");
            if (detail) detail.textContent = `${formatBytes(file.size)} · 解析所要 ${elapsed}s`;
          }
        }
        setState("done");
      } else {
        setState("ready");
      }
    }
  });

  // ---- scan: POST + SSE consumer ------------------------------------
  const scanForm = document.getElementById("scan-form");
  const scanResultArea = document.getElementById("scan-result-area");
  if (scanForm && scanResultArea) {
    scanForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const pathInput = document.getElementById("scan-path");
      const rel = pathInput.value.trim();
      if (!rel) return;
      startScan(rel, scanResultArea);
    });
  }

  async function startScan(rel, targetEl) {
    targetEl.innerHTML = `<p class="scan-status"><span class="spinner"></span> "${escapeHtml(rel)}" を解析準備中…</p>`;
    let resp;
    try {
      resp = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: [rel] }),
      });
    } catch (err) {
      targetEl.innerHTML = renderError({ error: "NetworkError", detail: String(err) });
      return;
    }
    const data = await resp.json();
    if (!resp.ok) {
      targetEl.innerHTML = renderError(data);
      return;
    }
    targetEl.innerHTML = renderProgressShell(data);
    initScanCharts(targetEl);
    consumeSse(data.job_id, targetEl);
  }

  function consumeSse(jobId, targetEl) {
    const counts = { OK: 0, WARN: 0, FAIL: 0 };
    const startedAt = performance.now();
    const elapsedEl = targetEl.querySelector(".scan-elapsed");
    const tickHandle = setInterval(() => {
      if (elapsedEl) {
        elapsedEl.textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)}s`;
      }
    }, 100);
    const finalElapsed = () => ((performance.now() - startedAt) / 1000).toFixed(2);
    const sse = new EventSource(`/api/scan/${jobId}/events`);
    sse.addEventListener("file_done", (e) => {
      const payload = JSON.parse(e.data);
      appendRow(targetEl, payload);
      counts[payload.verdict] = (counts[payload.verdict] || 0) + 1;
      updateVerdictDonut(targetEl, counts);
      extendDeltaScatter(targetEl, payload);
    });
    sse.addEventListener("done", () => {
      sse.close();
      clearInterval(tickHandle);
      if (elapsedEl) elapsedEl.textContent = `${finalElapsed()}s`;
      finalize(targetEl, jobId);
    });
    sse.addEventListener("error", () => {
      sse.close();
      clearInterval(tickHandle);
      const state = targetEl.querySelector(".scan-state");
      if (state) {
        state.textContent = "sse error";
        state.className = "scan-state scan-state--failed";
      }
    });
  }

  // ---- chart scaffolding (scan side) --------------------------------
  function initScanCharts(targetEl) {
    if (typeof Plotly === "undefined") return;
    const donutEl = targetEl.querySelector(".chart-verdict-donut");
    const scatterEl = targetEl.querySelector(".chart-delta-scatter");
    if (donutEl) {
      Plotly.newPlot(
        donutEl,
        [
          {
            type: "pie",
            hole: 0.55,
            labels: [verdictLabel("OK"), verdictLabel("WARN"), verdictLabel("FAIL")],
            values: [0, 0, 0],
            marker: { colors: [PALETTE.ok, PALETTE.warn, PALETTE.fail] },
            textposition: "inside",
            hovertemplate: "%{label}: %{value} (%{percent})<extra></extra>",
          },
        ],
        sharedLayout("視聴判定の内訳", { showlegend: true, legend: { orientation: "h", y: -0.1 } }),
        PLOTLY_OPTS,
      );
    }
    if (scatterEl) {
      Plotly.newPlot(
        scatterEl,
        [
          {
            type: "scatter",
            mode: "markers",
            x: [],
            y: [],
            text: [],
            marker: { color: PALETTE.neutral, size: 8 },
            hovertemplate: "#%{x} %{text}: %{y:+.2f} LU<extra></extra>",
          },
        ],
        sharedLayout("ファイルごとの ΔLU", {
          xaxis: { title: "ファイル番号", gridcolor: PALETTE.border },
          yaxis: { title: "ΔLU", zeroline: true, zerolinecolor: PALETTE.border, gridcolor: PALETTE.border },
        }),
        PLOTLY_OPTS,
      );
    }
  }

  function updateVerdictDonut(targetEl, counts) {
    if (typeof Plotly === "undefined") return;
    const donutEl = targetEl.querySelector(".chart-verdict-donut");
    if (!donutEl) return;
    Plotly.restyle(donutEl, { values: [[counts.OK, counts.WARN, counts.FAIL]] });
  }

  function extendDeltaScatter(targetEl, payload) {
    if (typeof Plotly === "undefined") return;
    if (payload.delta_lu_db === null || payload.delta_lu_db === undefined) return;
    const scatterEl = targetEl.querySelector(".chart-delta-scatter");
    if (!scatterEl) return;
    Plotly.extendTraces(
      scatterEl,
      { x: [[payload.sequence]], y: [[payload.delta_lu_db]], text: [[payload.source_name]] },
      [0],
    );
  }

  function sharedLayout(title, overrides) {
    return Object.assign(
      {
        title: { text: title, x: 0.02 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "rgba(255,255,255,0.02)",
        font: { color: PALETTE.fg, family: "system-ui, sans-serif" },
        margin: { l: 60, r: 24, t: 48, b: 64 },
        height: 280,
        showlegend: false,
      },
      overrides || {},
    );
  }

  function renderProgressShell(data) {
    return `
      <article class="scan-card" data-job-id="${data.job_id}">
        <header class="scan-card__header">
          <h3><span class="spinner"></span>解析中</h3>
          <code class="scan-job-id">${data.job_id}</code>
          <span class="scan-progress-counter">
            <span class="scan-done">0</span> / <span class="scan-total">${data.total_files}</span>
            ファイル · <span class="scan-elapsed">0.0s</span>
          </span>
        </header>
        <progress class="scan-progress-bar" max="${data.total_files}" value="0"></progress>
        <section class="charts">
          <div class="chart chart-verdict-donut"></div>
          <div class="chart chart-delta-scatter"></div>
        </section>
        <table class="scan-table">
          <thead><tr>
            <th>#</th><th>file</th><th>verdict</th><th>elapsed</th><th>flags</th>
          </tr></thead>
          <tbody class="scan-rows"></tbody>
        </table>
        <footer class="scan-card__footer">
          <span class="scan-state">running</span>
          <span class="scan-downloads" hidden>
            <a class="scan-download" data-ext="parquet">report.parquet</a>
            <a class="scan-download" data-ext="html">report.html</a>
          </span>
        </footer>
      </article>
    `;
  }

  function appendRow(targetEl, payload) {
    const tbody = targetEl.querySelector(".scan-rows");
    if (!tbody) return;
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${payload.sequence}</td>
      <td><code>${escapeHtml(payload.source_name)}</code></td>
      <td><span class="verdict verdict--${payload.verdict.toLowerCase()}">${escapeHtml(verdictLabel(payload.verdict))}</span></td>
      <td>${payload.elapsed_sec.toFixed(2)}s</td>
      <td>${payload.flag_codes.length}</td>
    `;
    tbody.appendChild(row);
    const bar = targetEl.querySelector(".scan-progress-bar");
    const done = targetEl.querySelector(".scan-done");
    if (bar) bar.value = payload.sequence;
    if (done) done.textContent = payload.sequence;
  }

  function finalize(targetEl, jobId) {
    const state = targetEl.querySelector(".scan-state");
    const downloads = targetEl.querySelector(".scan-downloads");
    const heading = targetEl.querySelector(".scan-card__header h3");
    if (heading) heading.textContent = "完了";  // remove spinner
    if (state) {
      state.textContent = "done";
      state.className = "scan-state scan-state--done";
    }
    if (downloads) {
      downloads.querySelectorAll(".scan-download").forEach((a) => {
        a.href = `/api/scan/${jobId}/report.${a.dataset.ext}`;
      });
      downloads.hidden = false;
    }
  }

  function renderError(data) {
    const detail = data && data.detail ? data.detail : "unknown error";
    const error = data && data.error ? data.error : "Error";
    return `
      <article class="error-card">
        <h3>${escapeHtml(error)}</h3>
        <p>${escapeHtml(detail)}</p>
      </article>
    `;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    })[c]);
  }
})();
