import { LogLevel } from "@azure/msal-browser";

const tenantId = import.meta.env.VITE_TENANT_ID || "";
const clientId = import.meta.env.VITE_CLIENT_ID || "";
const apiScope = import.meta.env.VITE_API_SCOPE || "";

export const msalConfig = {
  auth: {
    clientId,
    authority: tenantId
      ? `https://login.microsoftonline.com/${tenantId}`
      : "https://login.microsoftonline.com/common",
    redirectUri: window.location.origin,
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "localStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
      loggerCallback: (_level, message) => console.warn(message),
    },
  },
};

export const loginRequest = {
  scopes: apiScope ? [apiScope] : [],
};

export const isAuthEnabled = Boolean(clientId && tenantId);
