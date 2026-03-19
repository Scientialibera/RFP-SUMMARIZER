import React from "react";
import { createRoot } from "react-dom/client";
import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { msalConfig, isAuthEnabled } from "./auth/msalConfig";
import App from "./App.jsx";
import "./index.css";

const msalInstance = new PublicClientApplication(msalConfig);

function Root() {
  if (!isAuthEnabled) {
    return <App />;
  }
  return (
    <MsalProvider instance={msalInstance}>
      <App />
    </MsalProvider>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
