// Three pieces of progressive enhancement glue:
//   1. Tab switching (Inspect ↔ Scan).
//   2. Drag-and-drop on the inspect drop-zone.
//   3. Scan form submission + SSE consumer (per-file rows + downloads).
//
// Everything degrades gracefully — without JS the inspect form still works
// (HTMX); the scan form posts to /api/scan but cannot render live progress.

(() => {
  "use strict";

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

  // ---- inspect drop-zone --------------------------------------------
  const drop = document.querySelector(".drop-zone");
  const input = document.getElementById("file-input");
  const inspectForm = document.getElementById("inspect-form");
  if (drop && input && inspectForm) {
    const stop = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    ["dragenter", "dragover"].forEach((evt) =>
      drop.addEventListener(evt, (e) => {
        stop(e);
        drop.classList.add("dragover");
      }),
    );
    ["dragleave", "drop"].forEach((evt) =>
      drop.addEventListener(evt, (e) => {
        stop(e);
        drop.classList.remove("dragover");
      }),
    );
    drop.addEventListener("drop", (e) => {
      const files = e.dataTransfer && e.dataTransfer.files;
      if (!files || files.length === 0) return;
      input.files = files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      inspectForm.requestSubmit();
    });
  }

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
    targetEl.innerHTML = `<p class="scan-status">⏳ resolving "${escapeHtml(rel)}"…</p>`;
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
    consumeSse(data.job_id, targetEl);
  }

  function consumeSse(jobId, targetEl) {
    const sse = new EventSource(`/api/scan/${jobId}/events`);
    sse.addEventListener("file_done", (e) => {
      const payload = JSON.parse(e.data);
      appendRow(targetEl, payload);
    });
    sse.addEventListener("done", () => {
      sse.close();
      finalize(targetEl, jobId);
    });
    sse.addEventListener("error", () => {
      sse.close();
      const state = targetEl.querySelector(".scan-state");
      if (state) {
        state.textContent = "sse error";
        state.className = "scan-state scan-state--failed";
      }
    });
  }

  function renderProgressShell(data) {
    return `
      <article class="scan-card" data-job-id="${data.job_id}">
        <header class="scan-card__header">
          <h3>Scan job</h3>
          <code class="scan-job-id">${data.job_id}</code>
          <span class="scan-progress-counter">
            <span class="scan-done">0</span> / <span class="scan-total">${data.total_files}</span>
          </span>
        </header>
        <progress class="scan-progress-bar" max="${data.total_files}" value="0"></progress>
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
      <td><span class="verdict verdict--${payload.verdict.toLowerCase()}">${payload.verdict}</span></td>
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
