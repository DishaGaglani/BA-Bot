import React, { useState, useEffect } from 'react';

interface ProjectDetailsProps {
  token: string;
  projectId: number;
  onBack: () => void;
  users: any[];
}

interface Member {
  id: number;
  name: string;
  email: string;
  project_role: string;
}

interface Document {
  id: number;
  timestamp: string;
  action: string;
  format: string;
  triggered_by: string;
}

interface Message {
  id: number;
  role: string;
  text: string;
  created_at: string;
}

interface ActivityLog {
  id: number;
  action: string;
  user_email: string;
  timestamp: string;
  metadata: any;
}

interface ProjectDetailState {
  overview: {
    id: number;
    name: string;
    description: string;
    department: string;
    business_unit: string;
    priority: string;
    start_date: string | null;
    end_date: string | null;
    status: string;
    tags: string;
    owner_name: string;
    owner_email: string;
    created_at: string;
  };
  members: Member[];
  documents: Document[];
  conversations: Message[];
  activity: ActivityLog[];
}

const ProjectDetails: React.FC<ProjectDetailsProps> = ({
  token,
  projectId,
  onBack,
  users
}) => {
  const [details, setDetails] = useState<ProjectDetailState | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'members' | 'documents' | 'conversations' | 'activity'>('overview');

  // Adding member form states
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [assignedRole, setAssignedRole] = useState('CONTRIBUTOR');
  const [isAddMemberOpen, setIsAddMemberOpen] = useState(false);

  const fetchDetails = async () => {
    setLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/details`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDetails(data);
      }
    } catch (err) {
      console.error('Failed to fetch project details', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchDetails();
  }, [projectId, token]);

  const handleToggleLock = async () => {
    if (!overview) return;
    try {
      const endpoint = overview.locked ? 'unlock' : 'lock';
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/${endpoint}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchDetails();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to toggle lock.');
      }
    } catch (err) {
      console.error(err);
      alert('Error toggling lock.');
    }
  };

  const handleRemoveMember = async (userId: number) => {
    if (!confirm('Are you sure you want to remove this user from the project?')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/members/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchDetails();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to remove user.');
      }
    } catch (err) {
      console.error(err);
      alert('Error removing user.');
    }
  };

  const handleChangeMemberRole = async (userId: number, role: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/members/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ role })
      });
      if (res.ok) {
        await fetchDetails();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to change role.');
      }
    } catch (err) {
      console.error(err);
      alert('Error changing user role.');
    }
  };

  const handleAddMembers = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedUserIds.length === 0) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/members`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          user_ids: selectedUserIds,
          role: assignedRole
        })
      });
      if (res.ok) {
        setIsAddMemberOpen(false);
        setSelectedUserIds([]);
        await fetchDetails();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to assign members.');
      }
    } catch (err) {
      console.error(err);
      alert('Error assigning members.');
    }
  };

  // Find users who are not already project members
  const nonMembers = details ? users.filter(u => {
    return !details.members.some(m => m.id === u.id);
  }) : [];

  if (loading) {
    return (
      <div style={{ padding: '24px' }}>
        <button onClick={onBack} className="admin-btn secondary small" style={{ marginBottom: '20px' }}>← Back to Projects</button>
        <div className="skeleton-container">
          <div className="skeleton-row" style={{ height: '100px' }} />
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      </div>
    );
  }

  if (!details) {
    return (
      <div style={{ padding: '24px', textAlign: 'center' }}>
        <button onClick={onBack} className="admin-btn secondary small" style={{ marginBottom: '20px' }}>← Back to Projects</button>
        <p>Project details could not be loaded.</p>
      </div>
    );
  }

  const { overview, members, documents, conversations, activity } = details;

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <button onClick={onBack} className="admin-btn secondary small" style={{ padding: '8px 14px' }}>← Back to Projects</button>
      </div>

      {/* OVERVIEW PANEL */}
      <div className="project-detail-header-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h1 style={{ margin: '0' }}>{overview.name}</h1>
              <span className={`badge ${overview.priority === 'CRITICAL' || overview.priority === 'HIGH' ? 'warning' : 'primary'}`}>
                {overview.priority} Priority
              </span>
              <span style={{
                fontSize: '0.8rem',
                padding: '4px 10px',
                borderRadius: '9999px',
                background: overview.status === 'APPROVED' ? '#d1fae5' : '#e0f2fe',
                color: overview.status === 'APPROVED' ? '#065f46' : '#0369a1',
                fontWeight: '600'
              }}>
                {overview.status}
              </span>
              {overview.locked && (
                <span style={{
                  fontSize: '0.8rem',
                  padding: '4px 10px',
                  borderRadius: '9999px',
                  background: '#ffe4e6',
                  color: '#be123c',
                  fontWeight: '600'
                }}>
                  🔒 Locked
                </span>
              )}
            </div>
            <p style={{ margin: '8px 0 0 0', color: '#64748b', fontSize: '0.9rem' }}>
              Managed by: <strong>{overview.owner_name}</strong> ({overview.owner_email})
            </p>
            <button
              onClick={handleToggleLock}
              className="admin-btn secondary small"
              style={{ marginTop: '8px' }}
            >
              {overview.locked ? '🔓 Unlock Workspace' : '🔒 Lock Workspace'}
            </button>
          </div>
          <div style={{ fontSize: '0.85rem', color: '#64748b', textAlign: 'right' }}>
            <div>Created: <strong>{new Date(overview.created_at).toLocaleDateString()}</strong></div>
            {overview.start_date && (
              <div>Timeline: <strong>{new Date(overview.start_date).toLocaleDateString()}</strong> - <strong>{overview.end_date ? new Date(overview.end_date).toLocaleDateString() : 'Active'}</strong></div>
            )}
          </div>
        </div>

        {overview.tags && (
          <div style={{ display: 'flex', gap: '6px', marginTop: '12px', flexWrap: 'wrap' }}>
            {overview.tags.split(',').map(tag => (
              <span key={tag} style={{ fontSize: '0.75rem', padding: '3px 8px', background: '#f1f5f9', color: '#334155', borderRadius: '6px', fontWeight: '500' }}>
                {tag.trim()}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* DETAIL TABS */}
      <div className="detail-tabs-bar" style={{ display: 'flex', borderBottom: '2px solid #e2e8f0', margin: '24px 0 20px 0', gap: '8px' }}>
        {(['overview', 'members', 'documents', 'conversations', 'activity'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveSubTab(tab)}
            style={{
              padding: '10px 16px',
              fontSize: '0.9rem',
              fontWeight: '600',
              background: 'none',
              border: 'none',
              borderBottom: activeSubTab === tab ? '3px solid var(--admin-primary)' : '3px solid transparent',
              color: activeSubTab === tab ? 'var(--admin-primary)' : '#64748b',
              cursor: 'pointer',
              textTransform: 'capitalize',
              marginBottom: '-2px'
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* TAB CONTENT PANELS */}
      <div className="table-card" style={{ padding: '24px' }}>
        
        {/* OVERVIEW SECTION */}
        {activeSubTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <h3 style={{ fontSize: '1.05rem', margin: '0 0 8px 0', color: '#0f172a' }}>Project Description</h3>
              <p style={{ color: '#334155', fontSize: '0.95rem', lineHeight: '1.6', margin: '0', background: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                {overview.description || 'No description provided.'}
              </p>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginTop: '8px' }}>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Department</div>
                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{overview.department || '—'}</div>
              </div>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Business Unit</div>
                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{overview.business_unit || '—'}</div>
              </div>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Assigned Members</div>
                <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#0f172a', marginTop: '4px' }}>{members.length} Users</div>
              </div>
            </div>
          </div>
        )}

        {/* MEMBERS SECTION */}
        {activeSubTab === 'members' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: '0', fontSize: '1.05rem', color: '#0f172a' }}>Project Collaboration Board</h3>
              <button 
                onClick={() => setIsAddMemberOpen(true)}
                className="admin-btn primary small"
              >
                👤 Add Team Member
              </button>
            </div>

            <table className="admin-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Project Role</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map(m => (
                  <tr key={m.id}>
                    <td>
                      <span style={{ fontWeight: '600', color: '#0f172a' }}>{m.name}</span>
                      {m.email === overview.owner_email && (
                        <span style={{ fontSize: '0.7rem', background: '#dbeafe', color: '#1e40af', padding: '2px 6px', borderRadius: '4px', marginLeft: '8px', fontWeight: 'bold' }}>
                          OWNER
                        </span>
                      )}
                    </td>
                    <td>{m.email}</td>
                    <td>
                      <select
                        value={m.project_role}
                        onChange={e => handleChangeMemberRole(m.id, e.target.value)}
                        disabled={m.email === overview.owner_email}
                        style={{ padding: '6px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', cursor: m.email === overview.owner_email ? 'not-allowed' : 'pointer', fontSize: '0.85rem', backgroundColor: '#fff' }}
                      >
                        <option value="PROJECT_MANAGER">Project Manager</option>
                        <option value="BUSINESS_ANALYST">Business Analyst</option>
                        <option value="CONTRIBUTOR">Contributor</option>
                        <option value="VIEWER">Viewer</option>
                      </select>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        onClick={() => handleRemoveMember(m.id)}
                        disabled={m.email === overview.owner_email}
                        className="admin-btn secondary small danger"
                        style={{ cursor: m.email === overview.owner_email ? 'not-allowed' : 'pointer' }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* GENERATED DOCUMENTS */}
        {activeSubTab === 'documents' && (
          <div>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Document Generation Logs</h3>
            {documents.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>
                No compliance document exports logged for this project yet.
              </div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Date / Time</th>
                    <th>Document Type</th>
                    <th>Log Action</th>
                    <th>Triggered By</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map(d => (
                    <tr key={d.id}>
                      <td>{new Date(d.timestamp).toLocaleString()}</td>
                      <td>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: d.format === 'PDF' ? '#fee2e2' : '#dbeafe',
                          color: d.format === 'PDF' ? '#991b1b' : '#1e40af',
                          fontWeight: 'bold',
                          fontSize: '0.75rem'
                        }}>
                          {d.format} File
                        </span>
                      </td>
                      <td>{d.action}</td>
                      <td>{d.triggered_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* RECENT CONVERSATIONS */}
        {activeSubTab === 'conversations' && (
          <div>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Dialogue Discovery History</h3>
            {conversations.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>
                No active conversations recorded inside this project workspace.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxHeight: '450px', overflowY: 'auto', padding: '10px', background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                {conversations.map(m => {
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
        )}

        {/* ACTIVITY FEED */}
        {activeSubTab === 'activity' && (
          <div>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Project Audit Log Timeline</h3>
            {activity.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>
                No logs recorded for this project yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {activity.map(al => (
                  <div key={al.id} style={{ display: 'flex', gap: '16px', paddingBottom: '12px', borderBottom: '1px solid #f1f5f9', fontSize: '0.85rem' }}>
                    <div style={{ color: '#64748b', minWidth: '130px' }}>
                      {new Date(al.timestamp).toLocaleString()}
                    </div>
                    <div>
                      User <strong>{al.user_email}</strong> triggered action:{' '}
                      <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px', color: '#e11d48', fontWeight: 'bold' }}>
                        {al.action}
                      </code>
                      {al.metadata && Object.keys(al.metadata).length > 0 && (
                        <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px', background: '#f8fafc', padding: '6px 10px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                          Metadata: {JSON.stringify(al.metadata)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ADD MEMBER MODAL */}
      {isAddMemberOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Add Workspace Member</h3>
              <button className="close-btn" onClick={() => setIsAddMemberOpen(false)}>×</button>
            </div>
            <form onSubmit={handleAddMembers}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {nonMembers.length === 0 ? (
                  <p style={{ color: '#64748b', fontSize: '0.9rem', textAlign: 'center' }}>
                    All registered users are already collaborators on this project.
                  </p>
                ) : (
                  <>
                    <p style={{ fontSize: '0.9rem', color: '#475569' }}>
                      Select one or more users to invite to this project's discovery board:
                    </p>
                    <label>
                      Select Users *
                      <select
                        multiple
                        value={selectedUserIds.map(String)}
                        onChange={e => {
                          const options = e.target.options;
                          const values: number[] = [];
                          for (let i = 0; i < options.length; i++) {
                            if (options[i].selected) {
                              values.push(Number(options[i].value));
                            }
                          }
                          setSelectedUserIds(values);
                        }}
                        required
                        style={{ width: '100%', minHeight: '120px', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
                      >
                        {nonMembers.map(u => (
                          <option key={u.id} value={u.id}>
                            {u.name} ({u.email}) — [{u.role}]
                          </option>
                        ))}
                      </select>
                      <span style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px', display: 'block' }}>
                        Hold Ctrl (Cmd on Mac) to select multiple users.
                      </span>
                    </label>

                    <label>
                      Assign Project Role *
                      <select 
                        value={assignedRole} 
                        onChange={e => setAssignedRole(e.target.value)}
                        style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff' }}
                      >
                        <option value="PROJECT_MANAGER">PROJECT_MANAGER</option>
                        <option value="BUSINESS_ANALYST">BUSINESS_ANALYST</option>
                        <option value="CONTRIBUTOR">CONTRIBUTOR</option>
                        <option value="VIEWER">VIEWER</option>
                      </select>
                    </label>
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="admin-btn secondary" onClick={() => setIsAddMemberOpen(false)}>Cancel</button>
                {nonMembers.length > 0 && (
                  <button type="submit" className="admin-btn primary">Add Selected Users</button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectDetails;
