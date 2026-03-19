import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import { loginRequest } from "./msalConfig";

export default function AuthGuard({ children }) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];

  const handleLogin = () => instance.loginPopup(loginRequest);
  const handleLogout = () =>
    instance.logoutPopup({ postLogoutRedirectUri: window.location.origin });

  return (
    <>
      <UnauthenticatedTemplate>
        <div className="auth-wall">
          <div className="auth-card">
            <h1>RFP Summarizer</h1>
            <p>Sign in with your Microsoft account to continue.</p>
            <button className="btn-primary" onClick={handleLogin}>
              Sign in
            </button>
          </div>
        </div>
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        <div className="auth-bar">
          <span className="auth-user">{account?.username}</span>
          <button className="auth-logout" onClick={handleLogout}>
            Sign out
          </button>
        </div>
        {children}
      </AuthenticatedTemplate>
    </>
  );
}
