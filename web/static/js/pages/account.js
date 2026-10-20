import { api } from "../api.js";
import { setTheme } from "../main.js";
import { setUser, store } from "../store.js";
import { avatar, clear, confirmDialog, errorMessage, fmt, formDialog, h, icon, modal, toast, fill } from "../ui.js";

export async function mount({ root }) {
  const tokensBox = h("div");
  const view = h("div");
  root.append(h("div.page-head", h("div", h("h1", "Minha conta"), h("p", "Perfil, aparência, senha e tokens para usar a API."))), view);

  function render() {
    const user = store.user;
    const name = h("input.input", { id: "acc-name", value: user.name, maxlength: 120 });
    const themeSeg = h("div.seg", { role: "group", "aria-label": "Tema" },
      [["system", "Igual ao sistema", "monitor"], ["light", "Claro", "sun"], ["dark", "Escuro", "moon"]].map(([value, label, ic]) =>
        h(`button${user.theme === value ? ".on" : ""}`, { type: "button", onclick: async () => { await setTheme(value); render(); } }, icon(ic, "sm"), label)));

    fill(view, h("div.settings",
      h("nav", h("a", { href: "#perfil" }, "Perfil"), h("a", { href: "#aparencia" }, "Aparência"), h("a", { href: "#senha" }, "Senha"), h("a", { href: "#tokens" }, "Tokens da API"), h("a", { href: "#atalhos" }, "Atalhos")),
      h("div",
        h("section.panel#perfil", h("div.panel-head", h("h2", "Perfil")), h("div.panel-body",
          h("div", { style: { display: "flex", gap: "14px", alignItems: "center", marginBottom: "18px" } }, avatar(user, "lg"),
            h("div", h("strong", user.name), h("div.muted", user.email))),
          h("div.field", h("label", { for: "acc-name" }, "Nome"), name),
          h("button.btn.primary", { onclick: async () => {
            try {
              setUser(await api("me", { method: "PATCH", body: { name: name.value.trim() } }));
              toast("Nome atualizado");
              render();
            } catch (err) {
              toast(errorMessage(err), "err");
            }
          } }, "Salvar"))),
        h("section.panel#aparencia", h("div.panel-head", h("h2", "Aparência")), h("div.panel-body",
          h("p.muted", { style: { marginBottom: "12px" } }, "O tema vale para todo o aplicativo. No leitor, escolha também a cor da página (papel, sépia ou noite)."), themeSeg)),
        h("section.panel#senha", h("div.panel-head", h("h2", "Senha")), h("div.panel-body",
          h("p.muted", { style: { marginBottom: "12px" } }, "Use pelo menos 8 caracteres, misturando letras e números."),
          h("button.btn", { onclick: changePassword }, icon("key", "sm"), "Trocar senha"))),
        h("section.panel#tokens", h("div.panel-head", h("h2", "Tokens da API"), h("button.btn.sm", { onclick: createToken }, icon("plus", "sm"), "Novo token")),
          h("div.panel-body", h("p.muted", { style: { marginBottom: "12px" } }, "Para scripts e integrações: envie no cabeçalho ", h("code", "Authorization: Bearer <token>"), ". O valor aparece uma única vez."), tokensBox)),
        h("section.panel#atalhos", h("div.panel-head", h("h2", "Atalhos de teclado")), h("div.panel-body", h("div.shortcuts",
          h("kbd", "/"), "Buscar na biblioteca",
          h("kbd", "U"), "Enviar documentos",
          h("span", h("kbd", "←"), " ", h("kbd", "→")), "Página anterior e próxima no leitor",
          h("span", h("kbd", "+"), " ", h("kbd", "−")), "Zoom (PDF) ou tamanho da letra (DOCX)",
          h("kbd", "F"), "Modo foco no leitor",
          h("span", h("kbd", "Ctrl"), " ", h("kbd", "F")), "Buscar dentro do documento",
          h("kbd", "Esc"), "Sair do modo foco e depois do leitor")))),
    ));
    view.querySelectorAll(".settings section").forEach((s) => (s.style.marginBottom = "18px"));
    loadTokens();
  }

  async function changePassword() {
    const done = await formDialog({
      title: "Trocar senha",
      submit: "Trocar",
      fields: [
        { name: "current", label: "Senha atual", type: "password", autocomplete: "current-password", required: true },
        { name: "new", label: "Nova senha", type: "password", autocomplete: "new-password", required: true },
      ],
      onSubmit: (values) => api("me/password", { method: "POST", body: values }),
    });
    if (done !== null && done !== undefined) toast("Senha alterada");
  }

  async function loadTokens() {
    const tokens = await api("me/tokens");
    fill(tokensBox, tokens.length
      ? h("table.table", h("tbody", tokens.map((t) => h("tr",
        h("td", h("strong", t.name), h("div.muted", { style: { fontSize: "12px", fontFamily: "var(--mono)" } }, `dl_${t.prefix}_…`)),
        h("td.muted", `Criado ${fmt.ago(t.created_at)}`),
        h("td.muted", t.last_used_at ? `Usado ${fmt.ago(t.last_used_at)}` : "Nunca usado"),
        h("td", { style: { textAlign: "right" } }, h("button.btn.ghost.sm.danger", { onclick: () => revoke(t) }, "Revogar"))))))
      : h("p.muted", "Nenhum token ativo."));
  }

  async function createToken() {
    const created = await formDialog({
      title: "Novo token",
      submit: "Criar",
      fields: [{ name: "name", label: "Para que serve?", placeholder: "Ex.: importação noturna", required: true, maxlength: 80 }],
      onSubmit: (values) => api("me/tokens", { method: "POST", body: values }),
    });
    if (!created) return;
    modal({
      title: "Copie o token agora",
      body: h("div", h("p", { style: { marginBottom: "12px" } }, "Por segurança, ele não será mostrado de novo."), h("div.token-box", created.token)),
      actions: [{
        label: "Copiar e fechar",
        kind: "primary",
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(created.token);
            toast("Token copiado");
          } catch {
            toast("Não foi possível copiar automaticamente. Selecione e copie o token.", "err");
            return false;
          }
        },
      }],
    });
    loadTokens();
  }

  async function revoke(token) {
    const ok = await confirmDialog({ title: "Revogar token?", text: `Scripts que usam “${token.name}” vão parar de funcionar.`, ok: "Revogar", danger: true });
    if (!ok) return;
    await api(`me/tokens/${token.id}`, { method: "DELETE" });
    loadTokens();
  }

  render();
  return null;
}
