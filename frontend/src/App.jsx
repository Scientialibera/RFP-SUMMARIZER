import { useEffect, useState } from "react";
import { useMsal } from "@azure/msal-react";

import AuthGuard from "./auth/AuthGuard";
import { isAuthEnabled } from "./auth/msalConfig";
import { setMsalContext } from "./auth/authFetch";
import Sidebar from "./components/Sidebar";
import RunHeader from "./components/RunHeader";
import ResultsTab from "./components/ResultsTab";
import ChunksTab from "./components/ChunksTab";
import ContextTab from "./components/ContextTab";
import SourceTab from "./components/SourceTab";
import AdminTab from "./components/AdminTab";
import useRfps from "./hooks/useRfps";
import useRun from "./hooks/useRun";
import useUser from "./hooks/useUser";

const TABS = [
  { id: "results", label: "Results" },
  { id: "chunks", label: "Chunks" },
  { id: "context", label: "Context" },
  { id: "source", label: "Source PDF" },
  { id: "admin", label: "Admin" },
];

function AppContent() {
  const { rfps, isLoading, error } = useRfps();
  const { isAdmin, loaded: userLoaded } = useUser();
  const [selectedRfpId, setSelectedRfpId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [activeTab, setActiveTab] = useState("results");

  const { run, isLoading: runLoading, error: runError } = useRun(selectedRunId);

  const selectedRfp = rfps.find((r) => r.id === selectedRfpId);

  useEffect(() => {
    if (!selectedRfpId && rfps.length) {
      setSelectedRfpId(rfps[0].id);
      setSelectedRunId(rfps[0].runs?.[0]?.id ?? "");
    }
  }, [rfps, selectedRfpId]);

  const handleSelectRun = (rfpId, runId) => {
    setSelectedRfpId(rfpId);
    setSelectedRunId(runId);
    setActiveTab("results");
  };

  const handleTabClick = (tabId) => {
    if (tabId === "admin" && !isAdmin) return;
    setActiveTab(tabId);
  };

  const showTabBar = run || activeTab === "admin";

  return (
    <div className="app-shell">
      <Sidebar
        rfps={rfps}
        selectedRfpId={selectedRfpId}
        selectedRunId={selectedRunId}
        isLoading={isLoading}
        onSelectRun={handleSelectRun}
      />
      <main className="main-content">
        {error && <div className="global-error">{error}</div>}

        {showTabBar && (
          <>
            {run && activeTab !== "admin" && (
              <RunHeader run={run} rfpName={selectedRfp?.name ?? ""} />
            )}
            <div className="tab-bar">
              {TABS.map((tab) => {
                const isDisabled = tab.id === "admin" && !isAdmin && userLoaded;
                return (
                  <button
                    key={tab.id}
                    className={`tab-btn ${activeTab === tab.id ? "active" : ""} ${isDisabled ? "disabled" : ""}`}
                    onClick={() => handleTabClick(tab.id)}
                    disabled={isDisabled}
                    title={isDisabled ? "Request the RFP.Admin role from your administrator to access this tab" : undefined}
                  >
                    {tab.label}
                    {tab.id === "chunks" && run?.chunk_files?.length > 0 && (
                      <span className="tab-count">{run.chunk_files.length}</span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="tab-content">
              {activeTab === "admin" && isAdmin && <AdminTab />}
              {activeTab === "results" && run && <ResultsTab result={run.result} />}
              {activeTab === "chunks" && run && (
                <ChunksTab runId={run.id} chunkFiles={run.chunk_files} />
              )}
              {activeTab === "context" && run && (
                <ContextTab runId={run.id} hasContext={run.has_context} />
              )}
              {activeTab === "source" && run && (
                <SourceTab runId={run.id} hasPdf={run.has_pdf} />
              )}
            </div>
          </>
        )}

        {!showTabBar && (
          <>
            {!selectedRunId ? (
              <div className="empty-main">
                <h2>Select a run to view results</h2>
                <p>Choose an RFP and run from the sidebar to get started.</p>
              </div>
            ) : runLoading ? (
              <div className="empty-main">
                <h2>Loading run details...</h2>
              </div>
            ) : runError ? (
              <div className="empty-main">
                <h2>Error loading run</h2>
                <p>{runError}</p>
              </div>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

export default function App() {
  if (isAuthEnabled) {
    return <AppWithAuth />;
  }
  return <AppContent />;
}

function AppWithAuth() {
  const { instance, accounts } = useMsal();

  useEffect(() => {
    setMsalContext(instance, accounts);
  }, [instance, accounts]);

  return (
    <AuthGuard>
      <AppContent />
    </AuthGuard>
  );
}
