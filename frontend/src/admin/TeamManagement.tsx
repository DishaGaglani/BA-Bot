import React, { useState, useEffect } from 'react';

interface UserData {
  id: number;
  name: string;
  email: string;
  role: string;
  team_id?: number | null;
}

interface ProjectData {
  id: number;
  name: string;
  status: string;
  department?: string;
  priority?: string;
}

interface TeamData {
  id: number;
  name: string;
  manager_id: number | null;
  manager_name: string;
  members_count: number;
  projects_count: number;
  created_at: string;
}

interface TeamAnalytics {
  teamName: string;
  managerName: string;
  members: { id: number; name: string; email: string; role: string }[];
  projects: { id: number; name: string; status: string; department: string; priority: string }[];
  messagesCount: number;
  activityCount: number;
  recentActivity: { id: number; action: string; user_email: string; timestamp: string }[];
}

interface TeamManagementProps {
  token: string;
  users: UserData[];
  projects: ProjectData[];
  onRefreshUsers: () => void;
}

const TeamManagement: React.FC<TeamManagementProps> = ({
  token,
  users,
  projects,
  onRefreshUsers
}) => {
  const [teams, setTeams] = useState<TeamData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Modals Toggles
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isMembersOpen, setIsMembersOpen] = useState(false);
  const [isProjectsOpen, setIsProjectsOpen] = useState(false);
  const [isAnalyticsOpen, setIsAnalyticsOpen] = useState(false);

  // Active Team variables
  const [activeTeam, setActiveTeam] = useState<TeamData | null>(null);
  const [teamName, setTeamName] = useState('');
  const [managerId, setManagerId] = useState<string>('');
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [selectedProjectIds, setSelectedProjectIds] = useState<number[]>([]);
  const [analytics, setAnalytics] = useState<TeamAnalytics | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [analyticsTab, setAnalyticsTab] = useState<'members' | 'projects' | 'activity'>('members');

  const fetchTeams = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/teams', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTeams(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchTeams();
  }, [token]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/teams', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: teamName,
          manager_id: managerId ? Number(managerId) : null
        })
      });
      if (res.ok) {
        setIsCreateOpen(false);
        setTeamName('');
        setManagerId('');
        await fetchTeams();
        onRefreshUsers();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to create team.');
      }
    } catch (err) {
      console.error(err);
      alert('Error creating team.');
    }
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTeam) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${activeTeam.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: teamName,
          manager_id: managerId ? Number(managerId) : null
        })
      });
      if (res.ok) {
        setIsEditOpen(false);
        setActiveTeam(null);
        setTeamName('');
        setManagerId('');
        await fetchTeams();
        onRefreshUsers();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to update team.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating team.');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this team? Members will be unassigned.')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchTeams();
        onRefreshUsers();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to delete team.');
      }
    } catch (err) {
      console.error(err);
      alert('Error deleting team.');
    }
  };

  const openMembers = (team: TeamData) => {
    setActiveTeam(team);
    // Find users currently belonging to this team
    const inTeam = users.filter(u => u.team_id === team.id).map(u => u.id);
    setSelectedUserIds(inTeam);
    setIsMembersOpen(true);
  };

  const handleSaveMembers = async () => {
    if (!activeTeam) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${activeTeam.id}/members`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ user_ids: selectedUserIds })
      });
      if (res.ok) {
        setIsMembersOpen(false);
        await fetchTeams();
        onRefreshUsers();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to assign members.');
      }
    } catch (err) {
      console.error(err);
      alert('Error assigning members.');
    }
  };

  const openProjects = async (team: TeamData) => {
    setActiveTeam(team);
    // Fetch current projects assigned to this team from backend database links
    setLoadingAnalytics(true);
    setIsProjectsOpen(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${team.id}/analytics`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data: TeamAnalytics = await res.json();
        setSelectedProjectIds(data.projects.map(p => p.id));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAnalytics(false);
    }
  };

  const handleSaveProjects = async () => {
    if (!activeTeam) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${activeTeam.id}/projects`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ project_ids: selectedProjectIds })
      });
      if (res.ok) {
        setIsProjectsOpen(false);
        await fetchTeams();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to assign projects.');
      }
    } catch (err) {
      console.error(err);
      alert('Error assigning projects.');
    }
  };

  const openAnalytics = async (team: TeamData) => {
    setActiveTeam(team);
    setLoadingAnalytics(true);
    setAnalytics(null);
    setIsAnalyticsOpen(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/teams/${team.id}/analytics`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAnalytics(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAnalytics(false);
    }
  };

  const filteredTeams = teams.filter(t => 
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.manager_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="admin-header-row">
        <div>
          <h1>Enterprise Teams Directory</h1>
          <p>Organize organizational divisions, managers, members and inherit automated workspace access.</p>
        </div>
        <button 
          onClick={() => {
            setTeamName('');
            setManagerId('');
            setIsCreateOpen(true);
          }} 
          className="admin-btn primary"
        >
          ➕ Create New Team
        </button>
      </div>

      {/* FILTER SEARCH BAR */}
      <div className="table-card" style={{ padding: '16px', marginTop: '20px' }}>
        <input
          type="text"
          placeholder="🔍 Search teams by name or manager..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: '100%', padding: '12px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.9rem' }}
        />
      </div>

      {/* TEAMS GRID TABLE */}
      <div className="table-card" style={{ marginTop: '20px' }}>
        {loading ? (
          <div className="skeleton-container">
            <div className="skeleton-row" style={{ height: '50px' }} />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        ) : filteredTeams.length === 0 ? (
          <div className="empty-state" style={{ padding: '60px 20px' }}>
            <div style={{ fontSize: '3.5rem', marginBottom: '16px' }}>👥</div>
            <h3>No Teams Established</h3>
            <p>Establish teams to group business analyst units and assign collective projects.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Team Name</th>
                  <th>Team Manager</th>
                  <th>Members Count</th>
                  <th>Projects Count</th>
                  <th>Created Date</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredTeams.map(t => (
                  <tr key={t.id}>
                    <td>
                      <div style={{ fontWeight: '600', color: '#0f172a' }}>{t.name}</div>
                    </td>
                    <td>
                      <span className="badge primary" style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
                        👤 {t.manager_name}
                      </span>
                    </td>
                    <td>
                      <strong>{t.members_count}</strong> Members
                    </td>
                    <td>
                      <strong>{t.projects_count}</strong> Projects
                    </td>
                    <td>
                      {new Date(t.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => openAnalytics(t)}
                          title="Telemetry Analytics"
                        >
                          📊 Analytics
                        </button>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => openMembers(t)}
                          title="Assign Members"
                        >
                          👥 Members
                        </button>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => openProjects(t)}
                          title="Assign Projects"
                        >
                          📁 Projects
                        </button>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => {
                            setActiveTeam(t);
                            setTeamName(t.name);
                            setManagerId(t.manager_id ? String(t.manager_id) : '');
                            setIsEditOpen(true);
                          }}
                          title="Rename/Edit"
                        >
                          ✏️
                        </button>
                        <button 
                          className="admin-btn secondary small danger" 
                          onClick={() => handleDelete(t.id)}
                          title="Delete Team"
                        >
                          🗑️
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

      {/* CREATE MODAL */}
      {isCreateOpen && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card" style={{ maxWidth: '500px' }}>
            <h2>Create New Team</h2>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.85rem' }}>
                Team Name
                <input
                  type="text"
                  required
                  value={teamName}
                  onChange={e => setTeamName(e.target.value)}
                  placeholder="e.g. HR Digitization Unit"
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontWeight: 'normal' }}
                />
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.85rem' }}>
                Team Manager
                <select
                  value={managerId}
                  onChange={e => setManagerId(e.target.value)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontWeight: 'normal', backgroundColor: '#fff' }}
                >
                  <option value="">-- Assign Manager (Optional) --</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                  ))}
                </select>
              </label>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" onClick={() => setIsCreateOpen(false)} className="admin-btn secondary">Cancel</button>
                <button type="submit" className="admin-btn primary">Create Team</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT/RENAME MODAL */}
      {isEditOpen && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card" style={{ maxWidth: '500px' }}>
            <h2>Rename & Edit Team</h2>
            <form onSubmit={handleEdit} style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '16px' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.85rem' }}>
                Team Name
                <input
                  type="text"
                  required
                  value={teamName}
                  onChange={e => setTeamName(e.target.value)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontWeight: 'normal' }}
                />
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontWeight: '600', fontSize: '0.85rem' }}>
                Team Manager
                <select
                  value={managerId}
                  onChange={e => setManagerId(e.target.value)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontWeight: 'normal', backgroundColor: '#fff' }}
                >
                  <option value="">-- Assign Manager (Optional) --</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                  ))}
                </select>
              </label>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" onClick={() => setIsEditOpen(false)} className="admin-btn secondary">Cancel</button>
                <button type="submit" className="admin-btn primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MANAGE MEMBERS MODAL */}
      {isMembersOpen && activeTeam && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card" style={{ maxWidth: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <h2>Assign Team Members: {activeTeam.name}</h2>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '4px 0 12px 0' }}>
              Select users to assign to this team. Moving a user already assigned to another team will re-assign their team membership.
            </p>

            <div style={{ overflowY: 'auto', flex: 1, border: '1px solid #cbd5e1', borderRadius: '6px', padding: '10px' }}>
              {users.map(u => {
                // Find user's current team name if any
                const currentTeam = teams.find(t => t.id === u.team_id);
                const isChecked = selectedUserIds.includes(u.id);

                return (
                  <label 
                    key={u.id} 
                    style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '12px', 
                      padding: '10px 8px', 
                      borderBottom: '1px solid #f1f5f9', 
                      cursor: 'pointer',
                      background: isChecked ? '#f8fafc' : 'transparent'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={e => {
                        if (e.target.checked) {
                          setSelectedUserIds([...selectedUserIds, u.id]);
                        } else {
                          setSelectedUserIds(selectedUserIds.filter(id => id !== u.id));
                        }
                      }}
                      style={{ width: '18px', height: '18px' }}
                    />
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: '0.9rem', fontWeight: '600' }}>{u.name}</span>
                      <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        {u.email} &bull; {u.role}
                        {currentTeam && (
                          <span style={{ marginLeft: '8px', color: currentTeam.id === activeTeam.id ? 'var(--admin-primary)' : '#b91c1c', fontWeight: 'bold' }}>
                            ({currentTeam.id === activeTeam.id ? 'Current Team' : `Moved from ${currentTeam.name}`})
                          </span>
                        )}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button type="button" onClick={() => setIsMembersOpen(false)} className="admin-btn secondary">Cancel</button>
              <button type="button" onClick={handleSaveMembers} className="admin-btn primary">Save Assignment</button>
            </div>
          </div>
        </div>
      )}

      {/* MANAGE PROJECTS MODAL */}
      {isProjectsOpen && activeTeam && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card" style={{ maxWidth: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <h2>Assign Workspace Projects: {activeTeam.name}</h2>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '4px 0 12px 0' }}>
              Map project workspaces to this team. All team members will inherit collaborative permissions to view and update details.
            </p>

            {loadingAnalytics ? (
              <div className="skeleton-container" style={{ flex: 1 }}>
                <div className="skeleton-row" />
                <div className="skeleton-row" />
              </div>
            ) : (
              <div style={{ overflowY: 'auto', flex: 1, border: '1px solid #cbd5e1', borderRadius: '6px', padding: '10px' }}>
                {projects.map(p => {
                  const isChecked = selectedProjectIds.includes(p.id);

                  return (
                    <label 
                      key={p.id} 
                      style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '12px', 
                        padding: '10px 8px', 
                        borderBottom: '1px solid #f1f5f9', 
                        cursor: 'pointer',
                        background: isChecked ? '#f8fafc' : 'transparent'
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={e => {
                          if (e.target.checked) {
                            setSelectedProjectIds([...selectedProjectIds, p.id]);
                          } else {
                            setSelectedProjectIds(selectedProjectIds.filter(id => id !== p.id));
                          }
                        }}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: '600' }}>{p.name}</span>
                        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                          Status: {p.status} &bull; Dept: {p.department || 'General'}
                        </span>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button type="button" onClick={() => setIsProjectsOpen(false)} className="admin-btn secondary">Cancel</button>
              <button type="button" onClick={handleSaveProjects} className="admin-btn primary">Save Assignment</button>
            </div>
          </div>
        </div>
      )}

      {/* TEAM TELEMETRY ANALYTICS MODAL */}
      {isAnalyticsOpen && activeTeam && (
        <div className="admin-modal-overlay">
          <div className="admin-modal-card" style={{ maxWidth: '800px', width: '90%', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
            <h2>📊 Team Telemetry Overview: {activeTeam.name}</h2>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '4px 0 14px 0' }}>
              Detailed workspace statistics, inherited user allocations, and transaction audit trails.
            </p>

            {loadingAnalytics ? (
              <div className="skeleton-container" style={{ flex: 1 }}>
                <div className="skeleton-row" style={{ height: '80px' }} />
                <div className="skeleton-row" />
                <div className="skeleton-row" />
              </div>
            ) : analytics ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', flex: 1, overflowY: 'auto' }}>
                {/* METRICS CARDS */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
                  <div style={{ padding: '16px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase' }}>Chat Messages Exchanges</div>
                    <div style={{ fontSize: '1.8rem', fontWeight: '800', color: 'var(--admin-primary)', marginTop: '4px' }}>
                      💬 {analytics.messagesCount}
                    </div>
                  </div>
                  <div style={{ padding: '16px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase' }}>Audited Event Actions</div>
                    <div style={{ fontSize: '1.8rem', fontWeight: '800', color: 'var(--admin-primary)', marginTop: '4px' }}>
                      ⚡ {analytics.activityCount}
                    </div>
                  </div>
                  <div style={{ padding: '16px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 'bold', textTransform: 'uppercase' }}>Associated Workspaces</div>
                    <div style={{ fontSize: '1.8rem', fontWeight: '800', color: 'var(--admin-primary)', marginTop: '4px' }}>
                      📂 {analytics.projects.length}
                    </div>
                  </div>
                </div>

                {/* HORIZONTAL TAB SWITCHER */}
                <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', gap: '20px' }}>
                  <button 
                    onClick={() => setAnalyticsTab('members')}
                    style={{
                      padding: '8px 2px',
                      background: 'none',
                      border: 'none',
                      borderBottom: analyticsTab === 'members' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                      color: analyticsTab === 'members' ? 'var(--admin-primary)' : '#64748b',
                      fontWeight: '600',
                      fontSize: '0.85rem',
                      cursor: 'pointer'
                    }}
                  >
                    👥 Team Members ({analytics.members.length})
                  </button>
                  <button 
                    onClick={() => setAnalyticsTab('projects')}
                    style={{
                      padding: '8px 2px',
                      background: 'none',
                      border: 'none',
                      borderBottom: analyticsTab === 'projects' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                      color: analyticsTab === 'projects' ? 'var(--admin-primary)' : '#64748b',
                      fontWeight: '600',
                      fontSize: '0.85rem',
                      cursor: 'pointer'
                    }}
                  >
                    📁 Assigned Projects ({analytics.projects.length})
                  </button>
                  <button 
                    onClick={() => setAnalyticsTab('activity')}
                    style={{
                      padding: '8px 2px',
                      background: 'none',
                      border: 'none',
                      borderBottom: analyticsTab === 'activity' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                      color: analyticsTab === 'activity' ? 'var(--admin-primary)' : '#64748b',
                      fontWeight: '600',
                      fontSize: '0.85rem',
                      cursor: 'pointer'
                    }}
                  >
                    ⚡ Recent Activity Log
                  </button>
                </div>

                {/* TAB PANELS */}
                <div style={{ flex: 1, minHeight: '200px' }}>
                  {analyticsTab === 'members' && (
                    <table className="admin-table" style={{ fontSize: '0.85rem' }}>
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Email</th>
                          <th>System Role</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.members.length === 0 ? (
                          <tr><td colSpan={3} style={{ textAlign: 'center', color: '#64748b' }}>No members assigned to this team.</td></tr>
                        ) : (
                          analytics.members.map(m => (
                            <tr key={m.id}>
                              <td><strong>{m.name}</strong> {m.name === analytics.managerName && <span style={{ fontSize: '0.7rem', padding: '1px 5px', background: '#ffe4e6', color: '#be123c', borderRadius: '4px', marginLeft: '6px' }}>Manager</span>}</td>
                              <td>{m.email}</td>
                              <td>{m.role}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  )}

                  {analyticsTab === 'projects' && (
                    <table className="admin-table" style={{ fontSize: '0.85rem' }}>
                      <thead>
                        <tr>
                          <th>Project Workspace</th>
                          <th>Status</th>
                          <th>Department</th>
                          <th>Priority</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.projects.length === 0 ? (
                          <tr><td colSpan={4} style={{ textAlign: 'center', color: '#64748b' }}>No projects mapped to this team.</td></tr>
                        ) : (
                          analytics.projects.map(p => (
                            <tr key={p.id}>
                              <td><strong>{p.name}</strong></td>
                              <td><span className={`badge ${p.status === 'APPROVED' ? 'success' : 'primary'}`}>{p.status}</span></td>
                              <td>{p.department}</td>
                              <td>{p.priority}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  )}

                  {analyticsTab === 'activity' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {analytics.recentActivity.length === 0 ? (
                        <div style={{ padding: '20px', textAlign: 'center', color: '#64748b' }}>No recent log events.</div>
                      ) : (
                        analytics.recentActivity.map(log => (
                          <div key={log.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #f1f5f9' }}>
                            <div>
                              <strong style={{ textTransform: 'capitalize' }}>{log.action}</strong>
                              <span style={{ fontSize: '0.75rem', color: '#64748b', marginLeft: '8px' }}>by {log.user_email}</span>
                            </div>
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{new Date(log.timestamp).toLocaleString()}</span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ padding: '20px', textAlign: 'center' }}>Error loading data.</div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px', borderTop: '1px solid #e2e8f0', paddingTop: '12px' }}>
              <button type="button" onClick={() => setIsAnalyticsOpen(false)} className="admin-btn secondary">Close Telemetry</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TeamManagement;
