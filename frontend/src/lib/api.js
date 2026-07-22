const BASE_URL = `${import.meta.env.VITE_API_URL}/api/auth`

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "request failed");
  }
  return data;
}

export function register(email, password) {
  return request("/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email, password) {
  return request("/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function me() {
  return request("/me", { method: "GET" });
}

export function logout() {
  return request("/logout", { method: "POST" });
}
