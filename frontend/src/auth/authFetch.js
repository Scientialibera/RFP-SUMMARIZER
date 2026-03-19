import { loginRequest, isAuthEnabled } from "./msalConfig";

let _msalInstance = null;
let _accounts = [];

export function setMsalContext(instance, accounts) {
  _msalInstance = instance;
  _accounts = accounts;
}

async function getToken() {
  if (!isAuthEnabled || !_msalInstance || !_accounts.length) return null;
  try {
    const response = await _msalInstance.acquireTokenSilent({
      ...loginRequest,
      account: _accounts[0],
    });
    return response.accessToken;
  } catch {
    const response = await _msalInstance.acquireTokenPopup(loginRequest);
    return response.accessToken;
  }
}

const apiBase = import.meta.env.VITE_API_BASE_URL || "";

export async function authFetch(path, options = {}) {
  const url = apiBase ? `${apiBase}${path}` : path;
  const headers = { ...(options.headers || {}) };

  const token = await getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return fetch(url, { ...options, headers });
}
