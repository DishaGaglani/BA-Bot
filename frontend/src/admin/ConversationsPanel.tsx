import React, { useState, useEffect } from 'react';

interface ConversationData {
  project_id: number;
  project_name: string;
  session_id: string;
  message_count: number;
  last_active: string | null;
}

interface Message {
  id: number;
  role: string;
  text: string;
  created_at: string;
}

interface ConversationsPanelProps {
  token: string;
}

const ConversationsPanel: React.FC<ConversationsPanelProps> = ({ token }) => {
  const [conversations, setConversations] = useState<ConversationData[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  // Dialog viewer states
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);

  const fetchConversations = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/conversations', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
      }
    } catch (err) {
      console.error('Failed to load conversations', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchConversations();
  }, [token]);

  const viewDialog = async (projectId: number) => {
    setSelectedProjectId(projectId);
    setLoadingMessages(true);
    setViewerOpen(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/details`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.conversations || []);
      }
    } catch (err) {
      console.error(err);
      alert('Error fetching chat messages.');
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleDeleteHistory = async (projectId: number) => {
    if (!confirm('Are you sure you want to clear this dialogue history? This will delete all chat messages in the session, but preserve the project metadata.')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/conversations/${projectId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchConversations();
        if (selectedProjectId === projectId) {
          setMessages([]);
        }
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to clear dialogue.');
      }
    } catch (err) {
      console.error(err);
      alert('Error clearing dialogue.');
    }
  };

  const filtered = conversations.filter(c => {
    return c.project_name.toLowerCase().includes(search.toLowerCase()) ||
           c.session_id.toLowerCase().includes(search.toLowerCase());
  });

  return (
    <div>
      <div className="admin-header-row">
        <h1>Discovery Conversations</h1>
        <p>Audit guided chatbot discovery logs and manage interactive session dialogues.</p>
      </div>

      {/* SEARCH CARD */}
      <div className="filters-card">
        <input
          type="text"
          placeholder="Search by project name or session ID..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="search-input"
          style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
        />
      </div>

      {/* TABLE */}
      <div className="table-card" style={{ marginTop: '20px' }}>
        {loading ? (
          <div className="skeleton-container">
            <div className="skeleton-row" style={{ height: '45px' }} />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state" style={{ padding: '50px 20px' }}>
            <div style={{ fontSize: '3.5rem', marginBottom: '16px' }}>💬</div>
            <h3>No Dialogues Logged</h3>
            <p>Active chat dialogue discovery sessions will appear here.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Project Name</th>
                  <th>Session ID</th>
                  <th>Total Messages</th>
                  <th>Last Active</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(c => (
                  <tr key={c.project_id}>
                    <td>
                      <span style={{ fontWeight: '600', color: '#0f172a' }}>{c.project_name}</span>
                    </td>
                    <td>
                      <code style={{ fontSize: '0.8rem', background: '#f1f5f9', padding: '3px 6px', borderRadius: '4px' }}>
                        {c.session_id}
                      </code>
                    </td>
                    <td>
                      <span style={{ fontWeight: '600', color: 'var(--admin-primary)' }}>
                        ⚡ {c.message_count} messages
                      </span>
                    </td>
                    <td>{c.last_active ? new Date(c.last_active).toLocaleString() : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => viewDialog(c.project_id)}
                        >
                          👁️ View Exchange
                        </button>
                        <button 
                          className="admin-btn secondary small danger" 
                          onClick={() => handleDeleteHistory(c.project_id)}
                        >
                          🗑️ Clear
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* VIEWER MODAL */}
      {viewerOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '800px', width: '90%' }}>
            <div className="modal-header">
              <h3>Dialogue Exchange History</h3>
              <button className="close-btn" onClick={() => setViewerOpen(false)}>×</button>
            </div>
            <div className="modal-body" style={{ padding: '20px' }}>
              {loadingMessages ? (
                <div className="skeleton-container" style={{ padding: '40px' }}>
                  <div className="skeleton-row" style={{ height: '30px', width: '70%' }} />
                  <div className="skeleton-row" style={{ height: '30px', width: '50%', alignSelf: 'flex-end' }} />
                  <div className="skeleton-row" style={{ height: '30px', width: '80%' }} />
                </div>
              ) : messages.length === 0 ? (
                <p style={{ textAlign: 'center', color: '#64748b', padding: '40px 0' }}>
                  Dialogue history is empty.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxHeight: '400px', overflowY: 'auto', padding: '12px', background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  {messages.map(m => {
                    const isUser = m.role === 'user';
                    return (
                      <div key={m.id} style={{ display: 'flex', flexDirection: 'column', alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '75%' }}>
                        <div style={{
                          padding: '12px 16px',
                          borderRadius: '12px',
                          background: isUser ? 'var(--admin-primary)' : '#fff',
                          color: isUser ? '#fff' : '#0f172a',
                          border: isUser ? 'none' : '1px solid #cbd5e1',
                          fontSize: '0.9rem',
                          lineHeight: '1.5',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                        }}>
                          {m.text}
                        </div>
                        <span style={{ fontSize: '0.7rem', color: '#64748b', alignSelf: isUser ? 'flex-end' : 'flex-start', marginTop: '4px' }}>
                          {isUser ? 'User' : 'AI Discoverer'} • {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="admin-btn primary" onClick={() => setViewerOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ConversationsPanel;
