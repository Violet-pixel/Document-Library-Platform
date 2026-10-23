import { api } from "../api.js";
import { on } from "../realtime.js";
import { STAGES, clear, confirmDialog, debounce, errorMessage, fmt, formDialog, h, icon, toast, fill } from "../ui.js";

const PROVIDERS = { local: "Resumo automático", anthropic: "Claude", openai: "API compatível com OpenAI" };

export async function mount({ root }) {
  const view = h("div");
  root.append(
    h("div.page-head", h("div", h("h1", "Sistema"), h("p", "Serviços, filas de processamento, provedor de IA e contas desta instalação.")),
      h("div.actions", h("a.btn", { href: "/api/docs", target: "_blank", rel: "noopener" }, icon("external", "sm"), "Documentação da API"))),
    view,
  );

  async function load() {
    const [data, users] = await Promise.all([api("system"), api("users")]);
    render(data, users);
  }

  function service(ic, name, detail, pill) {
    return h("div.service", h("span.ic", icon(ic)), h("div", h("strong", name), h("span", detail)), pill);
  }

  function render(data, users) {
    const docs = data.documents;
    const processing = docs.queued + docs.extracting + docs.describing;
    const proc = data.processor;
    const ai = data.ai;
    const day = data.last_24h;
    const workers = data.workers;
    const q = data.queues;

    const services = h("div.panel", h("div.panel-head", h("h2", "Serviços")), h("div.panel-body", { style: { paddingTop: "4px", paddingBottom: "4px" } },
      service("cpu", "Processador Java", proc.online ? `Versão ${proc.version}, PDFBox ${proc.pdfbox}. ${proc.busy} de ${proc.capacity} ocupados, média de ${fmt.ms(proc.avg_ms)}` : proc.error || "Sem resposta",
        h(`span.status-pill.${proc.online ? "ok" : "err"}`, proc.online ? "Online" : "Fora do ar")),
      service("server", "Workers do pipeline", workers.length ? workers.map((w) => `${w.name.split("-")[0]}: ${w.busy} de ${w.threads}`).join(", ") : "Nenhum worker ativo",
        h(`span.status-pill.${workers.length ? "ok" : "err"}`, `${workers.length} online`)),
      service("layers", "Filas (Redis Streams)", `Leitura: ${q.extract.waiting ?? 0} na fila, ${q.extract.pending} em andamento. Descrição: ${q.describe.waiting ?? 0} na fila, ${q.describe.pending} em andamento. ${q.delayed} aguardando nova tentativa.`,
        h(`span.status-pill.${q.delayed || q.extract.pending + q.describe.pending > 0 ? "warn" : "ok"}`, processing ? `${processing} processando` : "Em dia")),
      service("note", "Descrição por IA", [ai.label, ai.model, ai.base_url].filter(Boolean).join(", "),
        h(`span.status-pill.${ai.configured ? "ok" : "err"}`, ai.configured ? "Configurado" : "Falta configurar")),
    ));

    const usersPanel = h("div.panel", h("div.panel-head", h("h2", "Contas"), h("button.btn.sm", { onclick: () => editUser() }, icon("user-plus", "sm"), "Nova conta")),
      h("div", { style: { overflowX: "auto" } }, h("table.table",
        h("thead", h("tr", h("th", "Nome"), h("th", "Papel"), h("th", "Documentos"), h("th", "Último acesso"), h("th", ""))),
        h("tbody", users.map((u) => h("tr",
          h("td", h("strong", u.name), h("div.muted", { style: { fontSize: "12px" } }, u.email)),
          h("td", h(`span.status-pill${u.is_active ? "" : ".err"}`, u.is_active ? (u.role === "admin" ? "Administrador" : "Membro") : "Desativada")),
          h("td.num", fmt.n(u.document_count)),
          h("td.muted", fmt.ago(u.last_login)),
          h("td", { style: { textAlign: "right" } }, h("button.btn.ghost.sm", { onclick: () => editUser(u) }, "Editar"))))))));

    const jobs = h("div.panel", h("div.panel-head", h("h2", "Últimas etapas processadas")),
      h("div", { style: { overflowX: "auto" } }, h("table.table",
        h("thead", h("tr", h("th", "Documento"), h("th", "Etapa"), h("th", "Resultado"), h("th", "Tentativa"), h("th", "Duração"), h("th", "Quando"))),
        h("tbody", data.jobs.length ? data.jobs.map((j) => h("tr.row", { onclick: () => (location.href = `/documento/${j.document_id}`) },
          h("td", h("strong", { style: { fontWeight: 600 } }, j.document_title), j.error ? h("div", { style: { fontSize: "12px", color: "var(--danger)" } }, j.error.slice(0, 140)) : null),
          h("td", j.stage_label, j.details?.provider ? h("div.muted", { style: { fontSize: "12px" } }, j.details.model || PROVIDERS[j.details.provider] || j.details.provider) : null),
          h("td", h(`span.status-pill.${j.status === "succeeded" ? "ok" : j.status === "failed" ? "err" : "warn"}`, j.status_label)),
          h("td.num", j.attempt),
          h("td.num", fmt.ms(j.duration_ms)),
          h("td.muted", fmt.ago(j.started_at)))) : h("tr", h("td", { colspan: 6 }, h("span.muted", "Nada processado ainda.")))))));

    const failures = data.failures.length ? h("div.panel", { style: { marginBottom: "18px" } },
      h("div.panel-head", h("h2", `Documentos com erro (${data.failures.length})`), h("button.btn.sm", { onclick: retryAll }, icon("retry", "sm"), "Tentar todos de novo")),
      h("div.panel-body", data.failures.map((f) => h("div.service", h("span.ic", icon("alert")),
        h("div", h("strong", h("a", { href: `/documento/${f.id}` }, f.title)), h("span", f.detail || "Erro desconhecido")), h("span.muted", { style: { fontSize: "12px" } }, fmt.ago(f.updated_at)))))) : null;

    fill(view, 
      h("div.kpis",
        kpi("Documentos", fmt.n(data.storage.count), fmt.bytes(data.storage.bytes)),
        kpi("Prontos", fmt.n(docs.ready), `${fmt.n(processing)} processando`),
        kpi("Com erro", fmt.n(docs.failed), docs.failed ? "veja abaixo" : "nenhum"),
        kpi("Etapas em 24 h", fmt.n(day.succeeded), `${fmt.n(day.failed)} ${day.failed === 1 ? "falha" : "falhas"}, ${fmt.n(day.retried)} ${day.retried === 1 ? "nova tentativa" : "novas tentativas"}`),
        kpi("Leitura do arquivo", fmt.ms(day.extract_ms), `média; descrição em ${fmt.ms(day.describe_ms)}`)),
      h("div.two-col", services, usersPanel),
      failures,
      jobs,
    );
  }

  function kpi(label, value, sub) {
    return h("div.kpi", h("div.label", label), h("div.value", value), h("div.sub", sub));
  }

  async function retryAll() {
    const { requeued } = await api("system/retry-failed", { method: "POST" });
    toast(`${requeued} ${requeued === 1 ? "documento voltou" : "documentos voltaram"} para a fila`);
    load();
  }

  async function editUser(user) {
    const saved = await formDialog({
      title: user ? "Editar conta" : "Nova conta",
      submit: user ? "Salvar" : "Criar conta",
      fields: [
        { name: "name", label: "Nome", value: user?.name, required: true },
        { name: "email", label: "E-mail", type: "email", value: user?.email, required: true },
        { name: "role", label: "Papel", type: "select", value: user?.role || "member", options: [["member", "Membro"], ["admin", "Administrador"]] },
        { name: "is_active", label: "Situação", type: "select", value: user ? String(user.is_active) : "true", options: [["true", "Ativa"], ["false", "Desativada"]] },
        { name: "password", label: user ? "Nova senha" : "Senha inicial", type: "password", autocomplete: "new-password", hint: user ? "Deixe em branco para manter a atual." : "Mínimo de 8 caracteres." },
      ],
      onSubmit: (values) => {
        const body = { ...values, is_active: values.is_active === "true" };
        if (!body.password) delete body.password;
        return api(user ? `users/${user.id}` : "users", { method: user ? "PATCH" : "POST", body });
      },
    });
    if (saved) {
      toast(user ? "Conta atualizada" : "Conta criada");
      load();
    }
  }

  await load();
  const soon = debounce(() => load().catch(() => {}), 1500);
  const offs = [on("document.updated", soon), on("document.created", soon), on("document.deleted", soon)];
  const timer = setInterval(soon, 15000);
  return () => {
    offs.forEach((off) => off());
    clearInterval(timer);
  };
}
