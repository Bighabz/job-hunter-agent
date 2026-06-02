import { useState, useEffect, useCallback } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const STORAGE_KEY = "job-hunter:supabase-config";
const STATUS_COLORS = {
  saved: "#6b7280", intake: "#8b5cf6", tailored: "#6366f1", ready: "#3b82f6",
  applied: "#f59e0b", interviewing: "#10b981", offer: "#22c55e", rejected: "#ef4444", withdrawn: "#9ca3af",
};
const STATUS_ORDER = ["saved","intake","tailored","ready","applied","interviewing","offer","rejected","withdrawn"];

function StatusBadge({ status }) {
  const c = STATUS_COLORS[status] || "#6b7280";
  return (
    <span style={{
      display: "inline-block", padding: "2px 10px", borderRadius: "999px", fontSize: "11px",
      fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase",
      background: c + "22", color: c, border: `1px solid ${c}44`,
    }}>{status}</span>
  );
}

function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{
      background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px",
      padding: "20px 24px", flex: "1 1 0", minWidth: "140px",
    }}>
      <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "1.2px", color: "#6b6b80", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: "32px", fontWeight: 700, color: accent || "#e4e4ed", marginTop: "4px", fontFamily: "'JetBrains Mono', 'SF Mono', monospace" }}>{value}</div>
      {sub && <div style={{ fontSize: "12px", color: "#6b6b80", marginTop: "2px" }}>{sub}</div>}
    </div>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "8px", padding: "10px 14px", fontSize: "12px" }}>
      <div style={{ fontWeight: 600, marginBottom: "4px", color: "#e4e4ed" }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: p.color, display: "inline-block" }} />
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
}

export default function JobHunterDashboard() {
  const [config, setConfig] = useState({ url: "", key: "" });
  const [configSaved, setConfigSaved] = useState(false);
  const [apps, setApps] = useState([]);
  const [mats, setMats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [favOnly, setFavOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("table");

  useEffect(() => {
    (async () => {
      try {
        const r = await window.storage.get(STORAGE_KEY);
        if (r?.value) { const p = JSON.parse(r.value); setConfig(p); setConfigSaved(true); }
      } catch {}
    })();
  }, []);

  const saveConfig = async () => {
    if (!config.url || !config.key) return;
    try { await window.storage.set(STORAGE_KEY, JSON.stringify(config)); setConfigSaved(true); } catch { setError("Failed to save config"); }
  };

  const supa = useCallback(async (table, params = "") => {
    const u = config.url.replace(/\/$/, "");
    const r = await fetch(`${u}/rest/v1/${table}?${params}`, { headers: { apikey: config.key, Authorization: `Bearer ${config.key}` } });
    if (!r.ok) throw new Error(`Supabase ${r.status}`);
    return r.json();
  }, [config]);

  const supaUpdate = useCallback(async (table, id, body) => {
    const u = config.url.replace(/\/$/, "");
    const r = await fetch(`${u}/rest/v1/${table}?id=eq.${id}`, {
      method: "PATCH", headers: { apikey: config.key, Authorization: `Bearer ${config.key}`, "Content-Type": "application/json", Prefer: "return=minimal" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`Update failed`);
  }, [config]);

  const fetchData = useCallback(async () => {
    if (!config.url || !config.key) return;
    setLoading(true); setError(null);
    try {
      const [a, m] = await Promise.all([
        supa("applications", "select=*&order=created_at.desc"),
        supa("materials", "select=*&order=created_at.desc"),
      ]);
      setApps(a); setMats(m);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }, [config, supa]);

  useEffect(() => { if (configSaved) fetchData(); }, [configSaved, fetchData]);

  const toggleFav = async (app) => {
    const nv = !app.is_favorite;
    try { await supaUpdate("applications", app.id, { is_favorite: nv }); setApps(p => p.map(a => a.id === app.id ? { ...a, is_favorite: nv } : a)); } catch { setError("Failed to update"); }
  };

  const total = apps.length;
  const applied = apps.filter(a => !["saved","intake","tailored","ready"].includes(a.status)).length;
  const responses = apps.filter(a => a.response_received).length;
  const interviews = apps.filter(a => a.status === "interviewing").length;
  const offers = apps.filter(a => a.status === "offer").length;
  const rr = applied > 0 ? Math.round((responses / applied) * 100) : 0;
  const overdue = apps.filter(a => a.status === "applied" && a.follow_up_at && new Date(a.follow_up_at) < new Date()).length;

  const statusData = STATUS_ORDER.map(s => ({ name: s, count: apps.filter(a => a.status === s).length, fill: STATUS_COLORS[s] })).filter(d => d.count > 0);
  const platMap = {}; apps.forEach(a => { const p = a.platform || "Direct"; platMap[p] = (platMap[p] || 0) + 1; });
  const platData = Object.entries(platMap).map(([name, value]) => ({ name, value }));
  const PC = ["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#6366f1","#ec4899"];

  const filtered = apps.filter(a => {
    if (filter !== "all" && a.status !== filter) return false;
    if (favOnly && !a.is_favorite) return false;
    if (search) { const q = search.toLowerCase(); return (a.company?.toLowerCase().includes(q) || a.role_title?.toLowerCase().includes(q)); }
    return true;
  });

  const getMats = (id, type) => mats.filter(m => m.application_id === id && m.type === type);

  const inputStyle = { background: "#0a0a0f", border: "1px solid #1e1e2e", borderRadius: "8px", padding: "8px 14px", color: "#e4e4ed", fontSize: "12px", outline: "none" };
  const btnBase = { border: "1px solid #1e1e2e", borderRadius: "8px", padding: "8px 14px", cursor: "pointer", fontSize: "12px", fontWeight: 500 };

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, sans-serif", background: "#0a0a0f", color: "#e4e4ed", minHeight: "100vh" }}>
      {/* Header */}
      <div style={{ borderBottom: "1px solid #1e1e2e", padding: "20px 28px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <div style={{ fontSize: "20px", fontWeight: 700 }}><span style={{ color: "#3b82f6" }}>⬡</span> Job Hunter</div>
          <div style={{ fontSize: "12px", color: "#6b6b80", marginTop: "2px" }}>Application Pipeline & Analytics</div>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          {configSaved && <button onClick={fetchData} style={{ ...btnBase, background: "#12121a", color: "#e4e4ed" }}>↻ Refresh</button>}
          <button onClick={() => setConfigSaved(false)} style={{ ...btnBase, background: "transparent", color: "#6b6b80" }}>⚙</button>
        </div>
      </div>

      <div style={{ padding: "24px 28px", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Config Panel */}
        {!configSaved && (
          <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px", padding: "28px", marginBottom: "24px" }}>
            <div style={{ fontWeight: 600, marginBottom: "16px", fontSize: "14px" }}>Connect to Supabase</div>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <input value={config.url} onChange={e => setConfig(p => ({ ...p, url: e.target.value }))} placeholder="https://your-project.supabase.co" style={{ ...inputStyle, flex: "1 1 300px", padding: "10px 14px", fontSize: "13px" }} />
              <input value={config.key} onChange={e => setConfig(p => ({ ...p, key: e.target.value }))} placeholder="anon key" type="password" style={{ ...inputStyle, flex: "1 1 300px", padding: "10px 14px", fontSize: "13px" }} />
              <button onClick={saveConfig} style={{ background: "#3b82f6", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 24px", cursor: "pointer", fontWeight: 600, fontSize: "13px" }}>Connect</button>
            </div>
          </div>
        )}

        {error && <div style={{ background: "#ef444420", border: "1px solid #ef444444", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", fontSize: "13px", color: "#f87171" }}>⚠ {error}</div>}
        {loading && <div style={{ textAlign: "center", padding: "60px", color: "#6b6b80" }}>Loading pipeline data...</div>}

        {configSaved && !loading && (
          <>
            {/* Stats */}
            <div style={{ display: "flex", gap: "14px", marginBottom: "24px", flexWrap: "wrap" }}>
              <StatCard label="Total" value={total} />
              <StatCard label="Applied" value={applied} />
              <StatCard label="Response Rate" value={`${rr}%`} sub={`${responses} responses`} accent={rr > 20 ? "#10b981" : "#f59e0b"} />
              <StatCard label="Interviews" value={interviews + offers} accent="#10b981" />
              {overdue > 0 && <StatCard label="Overdue" value={overdue} accent="#ef4444" />}
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: "4px", marginBottom: "20px", borderBottom: "1px solid #1e1e2e" }}>
              {[["table","Applications"],["charts","Analytics"]].map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} style={{
                  background: tab === k ? "#12121a" : "transparent", border: tab === k ? "1px solid #1e1e2e" : "1px solid transparent",
                  borderBottom: tab === k ? "1px solid #12121a" : "none", borderRadius: "8px 8px 0 0",
                  padding: "10px 20px", cursor: "pointer", fontSize: "13px", fontWeight: 500,
                  color: tab === k ? "#e4e4ed" : "#6b6b80", marginBottom: "-1px",
                }}>{l}</button>
              ))}
            </div>

            {tab === "table" && (
              <>
                <div style={{ display: "flex", gap: "10px", marginBottom: "16px", flexWrap: "wrap", alignItems: "center" }}>
                  <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search company or role..." style={{ ...inputStyle, width: "220px" }} />
                  <select value={filter} onChange={e => setFilter(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                    <option value="all">All statuses</option>
                    {STATUS_ORDER.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <button onClick={() => setFavOnly(!favOnly)} style={{
                    ...btnBase, background: favOnly ? "#f59e0b22" : "#12121a",
                    borderColor: favOnly ? "#f59e0b44" : "#1e1e2e", color: favOnly ? "#f59e0b" : "#6b6b80",
                  }}>★ Favorites{favOnly ? " only" : ""}</button>
                  <span style={{ fontSize: "12px", color: "#6b6b80", marginLeft: "auto" }}>{filtered.length} of {total}</span>
                </div>

                <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px", overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid #1e1e2e" }}>
                          {["★","Company","Role","Status","Platform","Resume","CL","Applied","Follow-up","Link"].map(h => (
                            <th key={h} style={{ textAlign: "left", padding: "12px 14px", fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6b6b80", whiteSpace: "nowrap" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.length === 0 ? (
                          <tr><td colSpan={10} style={{ padding: "40px", textAlign: "center", color: "#6b6b80" }}>
                            {total === 0 ? "No applications yet — start applying!" : "No matches."}
                          </td></tr>
                        ) : filtered.map(app => {
                          const res = getMats(app.id, "resume");
                          const cls = getMats(app.id, "cover_letter");
                          const od = app.status === "applied" && app.follow_up_at && new Date(app.follow_up_at) < new Date();
                          return (
                            <tr key={app.id} style={{ borderBottom: "1px solid #1e1e2e", transition: "background 0.15s" }}
                              onMouseEnter={e => e.currentTarget.style.background = "#1a1a28"}
                              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                              <td style={{ padding: "10px 14px" }}>
                                <button onClick={() => toggleFav(app)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "16px", padding: 0, color: app.is_favorite ? "#f59e0b" : "#333" }}>★</button>
                              </td>
                              <td style={{ padding: "10px 14px", fontWeight: 600, whiteSpace: "nowrap" }}>{app.company}</td>
                              <td style={{ padding: "10px 14px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{app.role_title}</td>
                              <td style={{ padding: "10px 14px" }}><StatusBadge status={app.status} /></td>
                              <td style={{ padding: "10px 14px", color: "#6b6b80", fontSize: "12px" }}>{app.platform || "—"}</td>
                              <td style={{ padding: "10px 14px" }}>{res.length > 0 ? <span style={{ color: "#10b981", fontSize: "12px" }}>✓ {res.length}</span> : <span style={{ color: "#6b7280" }}>—</span>}</td>
                              <td style={{ padding: "10px 14px" }}>{cls.length > 0 ? <span style={{ color: "#10b981", fontSize: "12px" }}>✓ {cls.length}</span> : <span style={{ color: "#6b7280" }}>—</span>}</td>
                              <td style={{ padding: "10px 14px", fontSize: "12px", color: "#6b6b80", whiteSpace: "nowrap" }}>{app.applied_at ? new Date(app.applied_at).toLocaleDateString() : "—"}</td>
                              <td style={{ padding: "10px 14px", fontSize: "12px", whiteSpace: "nowrap", color: od ? "#ef4444" : "#6b6b80", fontWeight: od ? 600 : 400 }}>
                                {app.follow_up_at ? <>{new Date(app.follow_up_at).toLocaleDateString()}{od ? " ⚠" : ""}</> : "—"}
                              </td>
                              <td style={{ padding: "10px 14px" }}>
                                {app.jd_url ? <a href={app.jd_url} target="_blank" rel="noopener noreferrer" style={{ color: "#3b82f6", textDecoration: "none", fontSize: "12px" }}>View ↗</a> : "—"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}

            {tab === "charts" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px", padding: "24px" }}>
                  <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "16px" }}>Pipeline Breakdown</div>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={statusData} margin={{ left: -10 }}>
                      <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#6b6b80" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: "#6b6b80" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>{statusData.map((e, i) => <Cell key={i} fill={e.fill} />)}</Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px", padding: "24px" }}>
                  <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "16px" }}>By Platform</div>
                  {platData.length > 0 ? (
                    <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
                      <ResponsiveContainer width="50%" height={200}>
                        <PieChart><Pie data={platData} cx="50%" cy="50%" outerRadius={80} dataKey="value" strokeWidth={0}>
                          {platData.map((_, i) => <Cell key={i} fill={PC[i % PC.length]} />)}
                        </Pie><Tooltip /></PieChart>
                      </ResponsiveContainer>
                      <div style={{ fontSize: "12px" }}>
                        {platData.map((p, i) => (
                          <div key={p.name} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                            <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: PC[i % PC.length], flexShrink: 0 }} />
                            <span style={{ color: "#6b6b80" }}>{p.name}</span>
                            <span style={{ fontWeight: 600, marginLeft: "auto" }}>{p.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : <div style={{ textAlign: "center", color: "#6b6b80", padding: "60px 0" }}>No data yet</div>}
                </div>

                {/* Funnel */}
                <div style={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "12px", padding: "24px", gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "20px" }}>Conversion Funnel</div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flexWrap: "wrap", gap: "8px" }}>
                    {[
                      { label: "Applied", value: applied, color: "#f59e0b" },
                      { label: "Responded", value: responses, color: "#3b82f6" },
                      { label: "Interviewing", value: interviews, color: "#10b981" },
                      { label: "Offers", value: offers, color: "#22c55e" },
                    ].map((s, i) => (
                      <div key={s.label} style={{ display: "flex", alignItems: "center" }}>
                        <div style={{ textAlign: "center", minWidth: "110px" }}>
                          <div style={{ fontSize: "36px", fontWeight: 700, color: s.color, fontFamily: "'JetBrains Mono', monospace" }}>{s.value}</div>
                          <div style={{ fontSize: "11px", color: "#6b6b80", textTransform: "uppercase", letterSpacing: "1px", marginTop: "4px" }}>{s.label}</div>
                          {i > 0 && applied > 0 && <div style={{ fontSize: "11px", color: s.color, marginTop: "2px" }}>{Math.round((s.value / applied) * 100)}%</div>}
                        </div>
                        {i < 3 && <div style={{ color: "#1e1e2e", fontSize: "24px", margin: "0 8px" }}>→</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}