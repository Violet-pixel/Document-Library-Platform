(function () {
  var form = document.getElementById("login-form");
  var error = document.getElementById("form-error");
  var signup = false;
  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
  }
  var toggle = document.getElementById("switch");
  if (toggle) {
    toggle.addEventListener("click", function () {
      signup = !signup;
      document.getElementById("name-field").hidden = !signup;
      document.getElementById("form-title").textContent = signup ? "Criar conta" : "Entrar";
      document.getElementById("form-lead").textContent = signup
        ? "Crie sua conta para montar a sua biblioteca."
        : "Use seu e-mail e senha para acessar a biblioteca.";
      document.getElementById("submit").textContent = signup ? "Criar conta" : "Entrar";
      document.getElementById("switch-text").textContent = signup ? "Já tem conta?" : "Ainda não tem conta?";
      toggle.textContent = signup ? "Entrar" : "Criar conta";
      document.getElementById("password").autocomplete = signup ? "new-password" : "current-password";
      error.hidden = true;
    });
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var button = document.getElementById("submit");
    button.disabled = true;
    error.hidden = true;
    var body = { email: form.email.value.trim(), password: form.password.value };
    if (signup) body.name = form.name.value.trim();
    fetch(signup ? "/api/v1/auth/signup" : "/api/v1/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (res.ok) {
          var next = form.dataset.next || "/";
          window.location.href = next.charAt(0) === "/" && next.charAt(1) !== "/" ? next : "/";
          return;
        }
        error.textContent = (res.data && res.data.message) || "Não foi possível entrar.";
        error.hidden = false;
        button.disabled = false;
      })
      .catch(function () {
        error.textContent = "Sem conexão com o servidor.";
        error.hidden = false;
        button.disabled = false;
      });
  });
})();
