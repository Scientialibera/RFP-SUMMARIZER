import { useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";
import { formatRunDate } from "../utils/format";

export default function AdminTab() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState("");
  const [contentLoading, setContentLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch("/api/prompts");
        if (res.ok) setPrompts(await res.json());
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleSelect = async (blobPath) => {
    setSelected(blobPath);
    setDirty(false);
    setSaveStatus("");
    setContentLoading(true);
    try {
      const res = await authFetch(`/api/prompts/${blobPath}`);
      if (res.ok) setContent(await res.text());
      else setContent("(Failed to load)");
    } catch {
      setContent("(Error loading prompt)");
    } finally {
      setContentLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    setSaveStatus("");
    try {
      const res = await authFetch(`/api/prompts/${selected}`, {
        method: "PUT",
        headers: { "Content-Type": "text/plain" },
        body: content,
      });
      if (res.ok) {
        setSaveStatus("Saved successfully");
        setDirty(false);
        setPrompts((prev) =>
          prev.map((p) =>
            p.blob_path === selected
              ? { ...p, size: new Blob([content]).size, last_modified: new Date().toISOString() }
              : p,
          ),
        );
      } else {
        const err = await res.json().catch(() => ({}));
        setSaveStatus(`Error: ${err.detail || res.statusText}`);
      }
    } catch (e) {
      setSaveStatus(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="tab-empty">Loading prompts...</div>;
  }

  const promptFiles = prompts.filter((p) => p.blob_path.startsWith("prompts/"));
  const schemaFiles = prompts.filter((p) => p.blob_path.startsWith("schemas/"));

  return (
    <div className="admin-container">
      <div className="admin-header">
        <h2>Prompt & Schema Management</h2>
        <p className="admin-subtitle">
          Select a file to view and edit. Changes are saved to Azure Blob Storage.
        </p>
      </div>

      <div className="admin-layout">
        <div className="admin-file-list">
          {promptFiles.length > 0 && (
            <div className="admin-group">
              <h3>Prompts</h3>
              {promptFiles.map((p) => (
                <button
                  key={p.blob_path}
                  className={`admin-file-btn ${selected === p.blob_path ? "active" : ""}`}
                  onClick={() => handleSelect(p.blob_path)}
                >
                  <span className="admin-file-name">
                    {p.blob_path.split("/").pop()}
                  </span>
                  <span className="admin-file-meta">
                    {(p.size / 1024).toFixed(1)} KB
                    {p.last_modified && ` - ${formatRunDate(p.last_modified, "")}`}
                  </span>
                </button>
              ))}
            </div>
          )}

          {schemaFiles.length > 0 && (
            <div className="admin-group">
              <h3>Schemas</h3>
              {schemaFiles.map((p) => (
                <button
                  key={p.blob_path}
                  className={`admin-file-btn ${selected === p.blob_path ? "active" : ""}`}
                  onClick={() => handleSelect(p.blob_path)}
                >
                  <span className="admin-file-name">
                    {p.blob_path.split("/").pop()}
                  </span>
                  <span className="admin-file-meta">
                    {(p.size / 1024).toFixed(1)} KB
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="admin-editor">
          {!selected ? (
            <div className="admin-editor-empty">
              Select a prompt or schema file to edit
            </div>
          ) : contentLoading ? (
            <div className="admin-editor-empty">Loading...</div>
          ) : (
            <>
              <div className="admin-editor-header">
                <span className="admin-editor-path">{selected}</span>
                <div className="admin-editor-actions">
                  {saveStatus && (
                    <span
                      className={`admin-save-status ${saveStatus.startsWith("Error") ? "error" : "success"}`}
                    >
                      {saveStatus}
                    </span>
                  )}
                  <button
                    className="btn-primary"
                    onClick={handleSave}
                    disabled={saving || !dirty}
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
              <textarea
                className="admin-textarea"
                value={content}
                onChange={(e) => {
                  setContent(e.target.value);
                  setDirty(true);
                  setSaveStatus("");
                }}
                spellCheck={false}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
