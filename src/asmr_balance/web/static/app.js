// Drag-and-drop enrichment for the inspect form.
// When a file is dropped on the drop-zone, copy it into the hidden <input>
// and trigger the HTMX-bound submit. Pure progressive enhancement —
// clicking the label still works without JS.
(() => {
  "use strict";
  const drop = document.querySelector(".drop-zone");
  const input = document.getElementById("file-input");
  const form = document.getElementById("inspect-form");
  if (!drop || !input || !form) return;

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
    form.requestSubmit();
  });
})();
