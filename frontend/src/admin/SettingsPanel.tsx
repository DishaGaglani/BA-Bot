import React, { useState, useEffect } from 'react';

interface SettingsData {
  workspaceName: string;
  aiModel: string;
  tokenTimeout: number;
  allowRegistration: boolean;
  systemPrompt?: string;
}

interface SettingsPanelProps {
  token: string;
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({ token }) => {
  const [workspaceName, setWorkspaceName] = useState('');
  const [aiModel, setAiModel] = useState('');
  const [tokenTimeout, setTokenTimeout] = useState(3600);
  const [allowRegistration, setAllowRegistration] = useState(true);
  const [systemPrompt, setSystemPrompt] = useState('');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [activeSubTab, setActiveSubTab] = useState<'general' | 'prompts'>('general');

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/settings', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data: SettingsData = await res.json();
        setWorkspaceName(data.workspaceName);
        setAiModel(data.aiModel);
        setTokenTimeout(data.tokenTimeout);
        setAllowRegistration(data.allowRegistration);
        setSystemPrompt(data.systemPrompt || '');
      }
    } catch (err) {
      console.error('Failed to load settings', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchSettings();
  }, [token]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          workspaceName,
          aiModel,
          tokenTimeout,
          allowRegistration,
          systemPrompt
        })
      });
      if (res.ok) {
        setSuccessMsg('System configuration successfully updated and saved.');
        setTimeout(() => setSuccessMsg(''), 4000);
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to save settings.');
      }
    } catch (err) {
      console.error(err);
      alert('Error saving settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: '780px' }}>
      <div className="admin-header-row">
        <h1>System Configuration</h1>
        <p>Configure general workspace rules, system model targets, and system prompt guidelines.</p>
      </div>

      {/* FLUENT SUB-TABS */}
      <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: '20px', gap: '20px', marginTop: '16px' }}>
        <button 
          onClick={() => setActiveSubTab('general')}
          style={{
            padding: '10px 4px',
            background: 'none',
            border: 'none',
            borderBottom: activeSubTab === 'general' ? '2px solid var(--admin-primary)' : '2px solid transparent',
            color: activeSubTab === 'general' ? 'var(--admin-primary)' : '#64748b',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer',
            marginBottom: '-1px'
          }}
        >
          ⚙️ General Settings
        </button>
        <button 
          onClick={() => setActiveSubTab('prompts')}
          style={{
            padding: '10px 4px',
            background: 'none',
            border: 'none',
            borderBottom: activeSubTab === 'prompts' ? '2px solid var(--admin-primary)' : '2px solid transparent',
            color: activeSubTab === 'prompts' ? 'var(--admin-primary)' : '#64748b',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer',
            marginBottom: '-1px'
          }}
        >
          📝 Prompt Management
        </button>
      </div>

      {loading ? (
        <div className="skeleton-container" style={{ marginTop: '20px' }}>
          <div className="skeleton-row" style={{ height: '50px' }} />
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      ) : (
        <div className="table-card" style={{ padding: '24px', marginTop: '20px' }}>
          {successMsg && (
            <div style={{
              background: '#d1fae5',
              color: '#065f46',
              padding: '12px 16px',
              borderRadius: '8px',
              fontWeight: '600',
              fontSize: '0.85rem',
              marginBottom: '20px',
              border: '1px solid #a7f3d0'
            }}>
              ✅ {successMsg}
            </div>
          )}

          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            
            {activeSubTab === 'general' && (
              <>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.9rem', color: '#334155' }}>
                  Workspace Platform Name
                  <input
                    type="text"
                    value={workspaceName}
                    onChange={e => setWorkspaceName(e.target.value)}
                    required
                    placeholder="e.g. BA Bot Enterprise"
                    style={{ padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.9rem', fontWeight: 'normal' }}
                  />
                </label>

                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.9rem', color: '#334155' }}>
                  Discovery AI Model Target
                  <select
                    value={aiModel}
                    onChange={e => setAiModel(e.target.value)}
                    required
                    style={{ padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.9rem', fontWeight: 'normal', backgroundColor: '#fff' }}
                  >
                    <option value="Prediction Agent">Prediction Agent (Default)</option>
                    <option value="Gemini 1.5 Pro">Gemini 1.5 Pro</option>
                    <option value="Gemini 1.5 Flash">Gemini 1.5 Flash</option>
                    <option value="Custom Enterprise Agent">Custom Enterprise Agent</option>
                  </select>
                </label>

                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.9rem', color: '#334155' }}>
                  Session Token Timeout (Seconds)
                  <input
                    type="number"
                    value={tokenTimeout}
                    onChange={e => setTokenTimeout(Number(e.target.value))}
                    required
                    min="60"
                    style={{ padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.9rem', fontWeight: 'normal' }}
                  />
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '6px 0' }}>
                  <input
                    type="checkbox"
                    id="allow-reg-check"
                    checked={allowRegistration}
                    onChange={e => setAllowRegistration(e.target.checked)}
                    style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                  />
                  <label htmlFor="allow-reg-check" style={{ fontWeight: '600', fontSize: '0.9rem', color: '#334155', cursor: 'pointer' }}>
                    Permit Self Registration for Users
                  </label>
                </div>
              </>
            )}

            {activeSubTab === 'prompts' && (
              <>
                <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #cbd5e1', marginBottom: '10px' }}>
                  <span style={{ fontWeight: 'bold', fontSize: '0.85rem', color: '#1e293b', display: 'block', marginBottom: '4px' }}>
                    💡 Guide the Chatbot Discovery Prompt
                  </span>
                  <span style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: '1.4' }}>
                    The system prompt below instructs the AI agent during the structured workshop interviews. Keep instructions clear, specify section-by-section focus rules, and direct the agent to ask concise questions.
                  </span>
                </div>

                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.9rem', color: '#334155' }}>
                  Discovery Agent System Prompt
                  <textarea
                    value={systemPrompt}
                    onChange={e => setSystemPrompt(e.target.value)}
                    required
                    rows={12}
                    placeholder="Enter instructions for the AI discoverer agent..."
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      fontFamily: 'monospace',
                      lineHeight: '1.5',
                      fontWeight: 'normal',
                      resize: 'vertical'
                    }}
                  />
                </label>
              </>
            )}

            <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="submit"
                disabled={saving}
                className="admin-btn primary"
                style={{ minWidth: '120px' }}
              >
                {saving ? 'Saving...' : '💾 Save Settings'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

export default SettingsPanel;
