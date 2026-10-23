import { api, uploadFile } from "./api.js";
import { on } from "./realtime.js";
import { store } from "./store.js";
import { STAGES, errorMessage, fmt, h, icon, fill } from "./ui.js";

const ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const CONCURRENCY = 3;
const items = [];
let input;
let tray;
let list;
let title;
let context = { currentCollection: () => null };
let running = 0;

export function initUploads(ctx) {
  context = ctx;
  input = h("input", { type: "file", multiple: true, accept: ACCEPT, hidden: true });
  input.addEventListener("change", () => {
    addFiles([...input.files]);
    input.value = "";
  });
  document.body.append(input);
  initDropzone();
  on("document.updated", ({ id, status }) => track(id, status));
  on("document.created", ({ id, status }) => track(id, status));
}

export function pickFiles() {
  input?.click();
}

function initDropzone() {
  const zone = h("div.dropzone", { "aria-hidden": "true" },
    h("div.box", h("div.art", icon("file-up")), h("h2", "Solte para adicionar à biblioteca"),
      h("p", `PDF ou DOCX, até ${store.maxUploadMb} MB cada. O Lume gera a capa e a descrição logo depois do envio.`)));
  document.body.append(zone);
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  addEventListener("dragenter", (e) => {
    if (!hasFiles(e) || document.getElementById("app").hidden) return;
    depth += 1;
    zone.classList.add("show");
  });
  addEventListener("dragleave", (e) => {
    if (!hasFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (!depth) zone.classList.remove("show");
  });
  addEventListener("dragover", (e) => hasFiles(e) && e.preventDefault());
  addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    zone.classList.remove("show");
    if (!document.getElementById("app").hidden) addFiles([...e.dataTransfer.files]);
  });
}

export function addFiles(files) {
  const accepted = files.filter((f) => /\.(pdf|docx)$/i.test(f.name));
  const rejected = files.length - accepted.length;
  const collection = context.currentCollection();
  for (const file of accepted) {
    const item = { file, status: "uploading", progress: 0, id: null, message: "", collection };
    if (file.size > store.maxUploadMb * 1024 * 1024) {
      item.status = "error";
      item.message = `Passa do limite de ${store.maxUploadMb} MB`;
    }
    items.unshift(item);
  }
  if (rejected) {
    items.unshift({ file: { name: rejected === 1 ? "1 arquivo ignorado" : `${rejected} arquivos ignorados` }, status: "error", message: "Só PDF e DOCX são aceitos" });
  }
  renderTray();
  pump();
}

function pump() {
  while (running < CONCURRENCY) {
    const next = items.find((i) => i.status === "uploading" && !i.started);
    if (!next) break;
    next.started = true;
    running += 1;
    send(next).finally(() => {
      running -= 1;
      pump();
    });
  }
}

async function send(item) {
  try {
    const result = await uploadFile(item.file, {
      collection: item.collection,
      onProgress: (p) => {
        item.progress = p;
        renderItem(item);
      },
    });
    const doc = result.items[0];
    item.id = doc.id;
    item.duplicate = doc.duplicate;
    item.status = doc.duplicate ? "duplicate" : doc.status;
    item.progress = 1;
    window.dispatchEvent(new CustomEvent("library:uploaded", { detail: doc }));
  } catch (err) {
    item.status = "error";
    item.message = errorMessage(err);
  }
  renderTray();
}

function track(id, status) {
  const item = items.find((i) => i.id === id);
  if (!item || item.status === "duplicate") return;
  item.status = status;
  if (status === "failed") {
    api(`documents/${id}`).then((doc) => {
      item.message = doc.status_detail;
      renderItem(item);
    }).catch(() => {});
  }
  renderItem(item);
  renderTitle();
}

function stageText(item) {
  if (item.status === "uploading") return item.progress < 1 ? `Enviando ${Math.round(item.progress * 100)}% de ${fmt.bytes(item.file.size)}` : "Recebido, entrando na fila";
  if (item.status === "duplicate") return "Já estava na sua biblioteca";
  if (item.status === "error") return item.message;
  if (item.status === "failed") return item.message || "Não foi possível ler o arquivo";
  return STAGES[item.status] || item.status;
}

function renderItem(item) {
  if (!item.el) return;
  const done = item.status === "ready" || item.status === "duplicate";
  const bad = item.status === "error" || item.status === "failed";
  const pct = item.status === "uploading" ? item.progress * 40 : { queued: 55, extracting: 70, describing: 88 }[item.status] ?? 100;
  fill(item.el, 
    h(`span.ic${done ? ".ok" : bad ? ".err" : ""}`, done ? icon("check") : bad ? icon("alert") : h("span.spinner")),
    h("div", { style: { minWidth: 0 } },
      h("div.name", { title: item.file.name }, item.file.name),
      h(`div.stage${bad ? ".err" : ""}`, stageText(item)),
      !done && !bad ? h("div.bar", h("i", { style: { width: `${pct}%` } })) : null),
    done && item.id ? h("a.btn.sm.ghost", { href: `/documento/${item.id}` }, "Abrir") : h("span"),
  );
}

function renderTitle() {
  if (!title) return;
  const active = items.filter((i) => !["ready", "duplicate", "error", "failed"].includes(i.status)).length;
  title.textContent = active ? `Processando ${active} de ${items.length} ${items.length === 1 ? "arquivo" : "arquivos"}` : `${items.length} ${items.length === 1 ? "arquivo enviado" : "arquivos enviados"}`;
}

function renderTray() {
  if (!items.length) {
    tray?.remove();
    tray = null;
    return;
  }
  if (!tray) {
    title = h("span");
    list = h("div.tray-list");
    const toggle = h("button.btn.ghost.icon.sm", { "aria-label": "Recolher" }, icon("chevron-down"));
    toggle.addEventListener("click", () => {
      list.hidden = !list.hidden;
      toggle.style.transform = list.hidden ? "rotate(180deg)" : "";
    });
    const close = h("button.btn.ghost.icon.sm", { "aria-label": "Fechar", style: { marginLeft: "0" } }, icon("x"));
    close.addEventListener("click", () => {
      items.splice(0, items.length, ...items.filter((i) => i.status === "uploading"));
      renderTray();
    });
    tray = h("section.tray", { "aria-label": "Envios" }, h("div.tray-head", icon("upload", "sm"), title, toggle, close), list);
    document.body.append(tray);
  }
  list.replaceChildren(...items.map((item) => {
    item.el ||= h("div.tray-item");
    renderItem(item);
    return item.el;
  }));
  renderTitle();
}
