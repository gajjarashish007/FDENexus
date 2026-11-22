/* FDE Nexus: client for the Module 1 (Self-Service Portal) backend.
   Base URL resolution: localStorage "nx-api-base" > window.NX_API_BASE > same host, port 5001.
   The JWT lives in the nx-session object (field "token"). */
(function () {
  "use strict";
  const NX = window.NEXUS;

  function base() {
    return (localStorage.getItem("nx-api-base") || window.NX_API_BASE ||
      `${location.protocol}//${location.hostname || "localhost"}:5001`).replace(/\/$/, "");
  }
  function token() {
    try { return (JSON.parse(localStorage.getItem("nx-session") || "null") || {}).token || ""; }
    catch (e) { return ""; }
  }

  async function call(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const t = token();
    if (t) headers.Authorization = "Bearer " + t;
    let res;
    try {
      res = await fetch(base() + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    } catch (e) {
      const err = new Error("Cannot reach the portal backend at " + base() + ". Start it with ./start-portal.sh");
      err.network = true;
      throw err;
    }
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (res.status === 401 && t && !path.startsWith("/api/auth/login")) {
      localStorage.removeItem("nx-session");
      location.replace("login.html");
    }
    if (!res.ok) {
      const err = new Error(data.error || ("Request failed (" + res.status + ")"));
      err.status = res.status; err.details = data.details;
      throw err;
    }
    return data;
  }

  NX.api = {
    base,
    call,
    get: (p) => call("GET", p),
    post: (p, b) => call("POST", p, b || {}),
    health: () => call("GET", "/api/health"),
    login: (username, password) => call("POST", "/api/auth/login", { username, password }),
    signup: (username, email, password) => call("POST", "/api/auth/signup", { username, email, password, confirmPassword: password })
  };
})();
