/** Conexão WebSocket com reconexão automática. Emite os eventos do servidor em `bus`. */
export const bus = new EventTarget();
let socket;
let attempt = 0;
let pingTimer;

export function connect() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws/events`);
  socket.addEventListener("open", () => {
    const reconnected = attempt > 0;
    attempt = 0;
    bus.dispatchEvent(new CustomEvent("status", { detail: { online: true, reconnected } }));
    clearInterval(pingTimer);
    pingTimer = setInterval(() => socket.readyState === 1 && socket.send("ping"), 25000);
  });
  socket.addEventListener("message", (e) => {
    let data;
    try {
      data = JSON.parse(e.data);
    } catch {
      return;
    }
    if (data.type && data.type !== "pong" && data.type !== "hello") bus.dispatchEvent(new CustomEvent(data.type, { detail: data }));
    bus.dispatchEvent(new CustomEvent("any", { detail: data }));
  });
  socket.addEventListener("close", (e) => {
    clearInterval(pingTimer);
    bus.dispatchEvent(new CustomEvent("status", { detail: { online: false } }));
    if (e.code === 4401) return;
    attempt += 1;
    const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)) * (0.75 + Math.random() * 0.5);
    setTimeout(connect, delay);
  });
}

export function on(type, handler) {
  const listener = (e) => handler(e.detail);
  bus.addEventListener(type, listener);
  return () => bus.removeEventListener(type, listener);
}
