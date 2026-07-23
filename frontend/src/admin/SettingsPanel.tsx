import React, { useState, useEffect } from 'react';

interface SettingsData {
  workspaceName: string;
  aiModel: string;
  tokenTimeout: number;
  allowRegistration: boolean;
  systemPrompt?: string;
}

interface DiscoverySection {
  id: number;
  section_key: string;
  section_name: string;
  prompt: string;
  enabled: boolean;
  mandatory: boolean;
  question_order: number;
  default_value: string;
  validation_rules: string;
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

  const [discoverySections, setDiscoverySections] = useState<DiscoverySection[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [activeSubTab, setActiveSubTab] = useState<'general' | 'prompts' | 'discovery'>('general');

  // Editing Section Form states
  const [editingSectionId, setEditingSectionId] = useState<number | null>(null);
  const [editPrompt, setEditPrompt] = useState('');
  const [editEnabled, setEditEnabled] = useState(true);
  const [editMandatory, setEditMandatory] = useState(true);
  const [editOrder, setEditOrder] = useState(1);
  const [editDefaultVal, setEditDefaultVal] = useState('');
  const [editValidationRules, setEditValidationRules] = useState('');

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

  const fetchDiscoverySections = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/discovery-sections', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDiscoverySections(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    void fetchSettings();
    void fetchDiscoverySections();
  }, [token]);

  const handleSaveGeneral = async (e: React.FormEvent) => {
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

  const handleStartEditSection = (sec: DiscoverySection) => {
    setEditingSectionId(sec.id);
    setEditPrompt(sec.prompt);
    setEditEnabled(sec.enabled);
    setEditMandatory(sec.mandatory);
    setEditOrder(sec.question_order);
    setEditDefaultVal(sec.default_value);
    setEditValidationRules(sec.validation_rules);
  };

  const handleSaveSectionConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingSectionId === null) return;
    setSaving(true);
    setSuccessMsg('');
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/discovery-sections/${editingSectionId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          prompt: editPrompt,
          enabled: editEnabled,
          mandatory: editMandatory,
          question_order: editOrder,
          default_value: editDefaultVal,
          validation_rules: editValidationRules
        })
      });
      if (res.ok) {
        setEditingSectionId(null);
        await fetchDiscoverySections();
        setSuccessMsg('Discovery section configuration updated successfully.');
        setTimeout(() => setSuccessMsg(''), 4000);
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to save section details.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating section details.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: '820px' }}>
      <div className="admin-header-row">
        <h1>System Configuration</h1>
        <p>Configure general workspace rules, system model targets, prompt guidelines, and requirement sections.</p>
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
        <button 
          onClick={() => setActiveSubTab('discovery')}
          style={{
            padding: '10px 4px',
            background: 'none',
            border: 'none',
            borderBottom: activeSubTab === 'discovery' ? '2px solid var(--admin-primary)' : '2px solid transparent',
            color: activeSubTab === 'discovery' ? 'var(--admin-primary)' : '#64748b',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer',
            marginBottom: '-1px'
          }}
        >
          📋 Discovery Checklist Config
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

          {activeSubTab === 'general' && (
            <form onSubmit={handleSaveGeneral} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
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

              <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
                <button type="submit" disabled={saving} className="admin-btn primary" style={{ minWidth: '120px' }}>
                  {saving ? 'Saving...' : '💾 Save Settings'}
                </button>
              </div>
            </form>
          )}

          {activeSubTab === 'prompts' && (
            <form onSubmit={handleSaveGeneral} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
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

              <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
                <button type="submit" disabled={saving} className="admin-btn primary" style={{ minWidth: '120px' }}>
                  {saving ? 'Saving...' : '💾 Save Settings'}
                </button>
              </div>
            </form>
          )}

          {activeSubTab === 'discovery' && (
            <div>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #cbd5e1', marginBottom: '20px' }}>
                <span style={{ fontWeight: 'bold', fontSize: '0.85rem', color: '#1e293b', display: 'block', marginBottom: '4px' }}>
                  📋 Discovery Workshop Checklist Configuration
                </span>
                <span style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: '1.4' }}>
                  Configure the target requirement details gathered during interviews. Drag or change the Question Order index to direct the workshop flow. If a section is disabled, it is skipped dynamically.
                </span>
              </div>

              {editingSectionId !== null ? (
                <form onSubmit={handleSaveSectionConfig} style={{ display: 'flex', flexDirection: 'column', gap: '14px', background: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #cbd5e1' }}>
                  <h3 style={{ margin: '0 0 10px 0', fontSize: '0.95rem', fontWeight: 'bold' }}>
                    Configure: {discoverySections.find(s => s.id === editingSectionId)?.section_name}
                  </h3>

                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontWeight: '600', fontSize: '0.8rem' }}>
                    Section Eliciting Instruction Prompt
                    <textarea
                      required
                      value={editPrompt}
                      onChange={e => setEditPrompt(e.target.value)}
                      rows={5}
                      style={{ padding: '8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 'normal', fontSize: '0.85rem', fontFamily: 'monospace' }}
                    />
                  </label>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontWeight: '600', fontSize: '0.8rem' }}>
                      Question Order Flow
                      <input
                        type="number"
                        required
                        value={editOrder}
                        onChange={e => setEditOrder(Number(e.target.value))}
                        style={{ padding: '8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 'normal', fontSize: '0.85rem' }}
                      />
                    </label>

                    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontWeight: '600', fontSize: '0.8rem' }}>
                      Default Recommendation value (If user is unsure)
                      <input
                        type="text"
                        value={editDefaultVal}
                        onChange={e => setEditDefaultVal(e.target.value)}
                        style={{ padding: '8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 'normal', fontSize: '0.85rem' }}
                      />
                    </label>
                  </div>

                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontWeight: '600', fontSize: '0.8rem' }}>
                    Validation Rules
                    <input
                      type="text"
                      value={editValidationRules}
                      onChange={e => setEditValidationRules(e.target.value)}
                      placeholder="e.g. Minimum 20 characters length"
                      style={{ padding: '8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 'normal', fontSize: '0.85rem' }}
                    />
                  </label>

                  <div style={{ display: 'flex', gap: '20px', margin: '6px 0' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', fontWeight: '600', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={editEnabled}
                        onChange={e => setEditEnabled(e.target.checked)}
                      />
                      Enable this section
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', fontWeight: '600', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={editMandatory}
                        onChange={e => setEditMandatory(e.target.checked)}
                      />
                      Mandatory field
                    </label>
                  </div>

                  <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '10px' }}>
                    <button type="button" onClick={() => setEditingSectionId(null)} className="admin-btn secondary small">Cancel</button>
                    <button type="submit" disabled={saving} className="admin-btn primary small">
                      {saving ? 'Saving...' : '💾 Save Section'}
                    </button>
                  </div>
                </form>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="admin-table" style={{ fontSize: '0.85rem' }}>
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>Order</th>
                        <th>Section Title</th>
                        <th>Target Database Key</th>
                        <th>Mandatory</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {discoverySections.map(sec => (
                        <tr key={sec.id} style={{ opacity: sec.enabled ? 1 : 0.5 }}>
                          <td><strong>#{sec.question_order}</strong></td>
                          <td><strong>{sec.section_name}</strong></td>
                          <td><code>{sec.section_key}</code></td>
                          <td>
                            <span className={`badge ${sec.mandatory ? 'warning' : 'secondary'}`}>
                              {sec.mandatory ? 'Mandatory' : 'Optional'}
                            </span>
                          </td>
                          <td>
                            <span className={`badge ${sec.enabled ? 'success' : 'secondary'}`}>
                              {sec.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button 
                              onClick={() => handleStartEditSection(sec)}
                              className="admin-btn secondary small"
                            >
                              ⚙️ Configure
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SettingsPanel;
