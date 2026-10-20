export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `Erro ${status}`);
    this.status = status;
    this.body = body;
  }
}

export function csrfToken() {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
}

function buildUrl(path, query) {
  const url = new URL(path.startsWith("/") ? path : `/api/v1/${path}`, location.origin);
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== undefined && value !== null && value !== "" && value !== false) url.searchParams.set(key, value);
  }
  return url;
}

function expired() {
  location.href = `/entrar?next=${encodeURIComponent(location.pathname + location.search)}`;
}

export async function api(path, { method = "GET", body, query, signal } = {}) {
  const options = { method, credentials: "same-origin", headers: { Accept: "application/json" }, signal };
  if (body !== undefined) {
    if (body instanceof FormData) options.body = body;
    else {
      options.body = JSON.stringify(body);
      options.headers["Content-Type"] = "application/json";
    }
  }
  if (method !== "GET") options.headers["X-CSRFToken"] = csrfToken();
  const response = await fetch(buildUrl(path, query), options);
  if (response.status === 204) return null;
  const data = (response.headers.get("content-type") || "").includes("json") ? await response.json() : null;
  if (response.status === 401 || (response.status === 403 && data?.error === "not_authenticated")) {
    expired();
    throw new ApiError(response.status, data);
  }
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

/** Envio com progresso (fetch ainda não informa o progresso do upload). */
export function uploadFile(file, { visibility, collection, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("files", file);
    if (visibility) form.append("visibility", visibility);
    if (collection) form.append("collection", collection);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/documents");
    xhr.setRequestHeader("X-CSRFToken", csrfToken());
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* resposta sem JSON */
      }
      if (xhr.status === 401) return expired();
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(xhr.status, data?.errors?.[0] ? { message: data.errors[0].message } : data));
    };
    xhr.onerror = () => reject(new ApiError(0, { message: "Sem conexão com o servidor." }));
    xhr.send(form);
  });
}
