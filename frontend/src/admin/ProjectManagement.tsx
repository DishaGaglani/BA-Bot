import React, { useState, useEffect } from 'react';

export interface ProjectData {
  id: number;
  name: string;
  owner_id: number;
  owner_name: string;
  description: string;
  department: string;
  business_unit: string;
  priority: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  tags: string;
  member_count: number;
  created_at: string;
}

interface ProjectManagementProps {
  token: string;
  onSelectProject: (projectId: number) => void;
  users: any[];
}

const ProjectManagement: React.FC<ProjectManagementProps> = ({
  token,
  onSelectProject,
  users
}) => {
  const [projects, setProjects] = useState<ProjectData[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [deptFilter, setDeptFilter] = useState('');

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isTransferOpen, setIsTransferOpen] = useState(false);
  const [activeProject, setActiveProject] = useState<ProjectData | null>(null);

  // Form states
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [department, setDepartment] = useState('');
  const [businessUnit, setBusinessUnit] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [status, setStatus] = useState('DRAFT');
  const [tags, setTags] = useState('');
  const [newOwnerId, setNewOwnerId] = useState<number>(0);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/projects', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setProjects(data);
      }
    } catch (err) {
      console.error('Failed to load projects', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchProjects();
  }, [token]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/projects', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name,
          description,
          department,
          business_unit: businessUnit,
          priority,
          start_date: startDate || null,
          end_date: endDate || null,
          status,
          tags
        })
      });
      if (res.ok) {
        setIsCreateOpen(false);
        resetForm();
        await fetchProjects();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to create project.');
      }
    } catch (err) {
      console.error(err);
      alert('Error creating project.');
    }
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProject) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${activeProject.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name,
          description,
          department,
          business_unit: businessUnit,
          priority,
          start_date: startDate || null,
          end_date: endDate || null,
          status,
          tags
        })
      });
      if (res.ok) {
        setIsEditOpen(false);
        resetForm();
        await fetchProjects();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to update project.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating project.');
    }
  };

  const handleArchive = async (projectId: number) => {
    if (!confirm('Are you sure you want to archive this project?')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}/archive`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchProjects();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to archive project.');
      }
    } catch (err) {
      console.error(err);
      alert('Error archiving project.');
    }
  };

  const handleDelete = async (projectId: number) => {
    if (!confirm('WARNING: Deleting this project will remove all messages, members, and data associated with it. This cannot be undone. Proceed?')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${projectId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchProjects();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to delete project.');
      }
    } catch (err) {
      console.error(err);
      alert('Error deleting project.');
    }
  };

  const handleTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProject || !newOwnerId) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/projects/${activeProject.id}/transfer-ownership`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ owner_id: newOwnerId })
      });
      if (res.ok) {
        setIsTransferOpen(false);
        setActiveProject(null);
        await fetchProjects();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to transfer ownership.');
      }
    } catch (err) {
      console.error(err);
      alert('Error transferring ownership.');
    }
  };

  const openEdit = (p: ProjectData) => {
    setActiveProject(p);
    setName(p.name);
    setDescription(p.description || '');
    setDepartment(p.department || '');
    setBusinessUnit(p.business_unit || '');
    setPriority(p.priority || 'MEDIUM');
    setStartDate(p.start_date ? p.start_date.substring(0, 10) : '');
    setEndDate(p.end_date ? p.end_date.substring(0, 10) : '');
    setStatus(p.status || 'DRAFT');
    setTags(p.tags || '');
    setIsEditOpen(true);
  };

  const openTransfer = (p: ProjectData) => {
    setActiveProject(p);
    setNewOwnerId(p.owner_id);
    setIsTransferOpen(true);
  };

  const resetForm = () => {
    setActiveProject(null);
    setName('');
    setDescription('');
    setDepartment('');
    setBusinessUnit('');
    setPriority('MEDIUM');
    setStartDate('');
    setEndDate('');
    setStatus('DRAFT');
    setTags('');
  };

  // Filtered List
  const filteredProjects = projects.filter(p => {
    const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase()) ||
                          p.owner_name.toLowerCase().includes(search.toLowerCase()) ||
                          (p.tags && p.tags.toLowerCase().includes(search.toLowerCase()));
    const matchesPriority = !priorityFilter || p.priority === priorityFilter;
    const matchesDept = !deptFilter || p.department === deptFilter;
    return matchesSearch && matchesPriority && matchesDept;
  });

  const getPriorityBadgeClass = (pri: string) => {
    switch (pri) {
      case 'CRITICAL': return 'badge danger';
      case 'HIGH': return 'badge warning';
      case 'MEDIUM': return 'badge primary';
      case 'LOW': return 'badge secondary';
      default: return 'badge secondary';
    }
  };

  const getStatusBadgeClass = (stat: string) => {
    switch (stat) {
      case 'APPROVED': return 'badge success';
      case 'IN_REVIEW': return 'badge warning';
      case 'REJECTED': return 'badge danger';
      case 'ARCHIVED': return 'badge secondary';
      case 'DRAFT':
      default:
        return 'badge primary';
    }
  };

  return (
    <div>
      <div className="admin-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Projects Directory</h1>
          <p>Create, manage, and assign system discoverable projects.</p>
        </div>
        <button 
          className="admin-btn primary"
          onClick={() => { resetForm(); setIsCreateOpen(true); }}
        >
          ➕ Create Project
        </button>
      </div>

      {/* FILTER PANEL */}
      <div className="filters-card">
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', width: '100%' }}>
          <div style={{ flex: '1', minWidth: '240px' }}>
            <input
              type="text"
              placeholder="Search by project name, owner, or tags..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="search-input"
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
            />
          </div>
          <div style={{ width: '160px' }}>
            <select
              value={priorityFilter}
              onChange={e => setPriorityFilter(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', cursor: 'pointer', height: '42px', backgroundColor: '#fff' }}
            >
              <option value="">All Priorities</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>
          <div style={{ width: '180px' }}>
            <select
              value={deptFilter}
              onChange={e => setDeptFilter(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', cursor: 'pointer', height: '42px', backgroundColor: '#fff' }}
            >
              <option value="">All Departments</option>
              <option value="IT">IT</option>
              <option value="Finance">Finance</option>
              <option value="Operations">Operations</option>
              <option value="HR">HR</option>
              <option value="Marketing">Marketing</option>
              <option value="Engineering">Engineering</option>
            </select>
          </div>
        </div>
      </div>

      {/* PROJECTS TABLE */}
      <div className="table-card" style={{ marginTop: '20px' }}>
        {loading ? (
          <div className="skeleton-container">
            <div className="skeleton-row" style={{ height: '50px' }} />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        ) : filteredProjects.length === 0 ? (
          <div className="empty-state" style={{ padding: '60px 20px' }}>
            <div style={{ fontSize: '3.5rem', marginBottom: '16px' }}>📂</div>
            <h3>No Projects Found</h3>
            <p>Modify filters or click Create Project to establish a workspace.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Project Name</th>
                  <th>Owner</th>
                  <th>Department / BU</th>
                  <th>Priority</th>
                  <th>Timeline</th>
                  <th>Status</th>
                  <th>Members</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredProjects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div style={{ fontWeight: '600', color: '#0f172a' }}>{p.name}</div>
                      {p.tags && (
                        <div style={{ display: 'flex', gap: '4px', marginTop: '4px', flexWrap: 'wrap' }}>
                          {p.tags.split(',').map(tag => (
                            <span key={tag} style={{ fontSize: '0.7rem', padding: '2px 6px', background: '#f1f5f9', color: '#475569', borderRadius: '4px' }}>
                              {tag.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>{p.owner_name}</td>
                    <td>
                      <div style={{ fontWeight: '500' }}>{p.department || '—'}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{p.business_unit || '—'}</div>
                    </td>
                    <td>
                      <span className={getPriorityBadgeClass(p.priority)}>{p.priority}</span>
                    </td>
                    <td style={{ fontSize: '0.8rem' }}>
                      <div>S: {p.start_date ? p.start_date.substring(0, 10) : '—'}</div>
                      <div style={{ color: '#64748b' }}>E: {p.end_date ? p.end_date.substring(0, 10) : '—'}</div>
                    </td>
                    <td>
                      <span className={getStatusBadgeClass(p.status)}>{p.status}</span>
                    </td>
                    <td>
                      <div style={{ fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        👤 {p.member_count}
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => onSelectProject(p.id)}
                          title="View Details"
                        >
                          👁️ Details
                        </button>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => openEdit(p)}
                          title="Edit Project"
                        >
                          ✏️
                        </button>
                        <button 
                          className="admin-btn secondary small" 
                          onClick={() => openTransfer(p)}
                          title="Transfer Ownership"
                        >
                          🤝
                        </button>
                        {p.status !== 'ARCHIVED' && (
                          <button 
                            className="admin-btn secondary small" 
                            onClick={() => handleArchive(p.id)}
                            title="Archive Project"
                          >
                            📦
                          </button>
                        )}
                        <button 
                          className="admin-btn secondary small danger" 
                          onClick={() => handleDelete(p.id)}
                          title="Delete Project"
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
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Create New Project</h3>
              <button className="close-btn" onClick={() => setIsCreateOpen(false)}>×</button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <label>
                  Project Name *
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                    placeholder="Enter project name"
                  />
                </label>
                <label>
                  Description
                  <textarea
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    placeholder="Describe project requirements and objectives..."
                    style={{ width: '100%', minHeight: '80px', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
                  />
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Department
                    <select value={department} onChange={e => setDepartment(e.target.value)}>
                      <option value="">Select Dept</option>
                      <option value="IT">IT</option>
                      <option value="Finance">Finance</option>
                      <option value="Operations">Operations</option>
                      <option value="HR">HR</option>
                      <option value="Marketing">Marketing</option>
                      <option value="Engineering">Engineering</option>
                    </select>
                  </label>
                  <label>
                    Business Unit
                    <input
                      type="text"
                      value={businessUnit}
                      onChange={e => setBusinessUnit(e.target.value)}
                      placeholder="e.g. Retail Bank"
                    />
                  </label>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Priority
                    <select value={priority} onChange={e => setPriority(e.target.value)}>
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </label>
                  <label>
                    Project Status
                    <select value={status} onChange={e => setStatus(e.target.value)}>
                      <option value="DRAFT">DRAFT</option>
                      <option value="IN_REVIEW">IN_REVIEW</option>
                      <option value="APPROVED">APPROVED</option>
                      <option value="REJECTED">REJECTED</option>
                    </select>
                  </label>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Start Date
                    <input
                      type="date"
                      value={startDate}
                      onChange={e => setStartDate(e.target.value)}
                    />
                  </label>
                  <label>
                    End Date
                    <input
                      type="date"
                      value={endDate}
                      onChange={e => setEndDate(e.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Tags (comma-separated)
                  <input
                    type="text"
                    value={tags}
                    onChange={e => setTags(e.target.value)}
                    placeholder="e.g. Core Banking, Migration, Q3"
                  />
                </label>
              </div>
              <div className="modal-footer">
                <button type="button" className="admin-btn secondary" onClick={() => setIsCreateOpen(false)}>Cancel</button>
                <button type="submit" className="admin-btn primary">Create Project</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {isEditOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Edit Project Details</h3>
              <button className="close-btn" onClick={() => setIsEditOpen(false)}>×</button>
            </div>
            <form onSubmit={handleEdit}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <label>
                  Project Name *
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                    placeholder="Enter project name"
                  />
                </label>
                <label>
                  Description
                  <textarea
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    placeholder="Describe project requirements and objectives..."
                    style={{ width: '100%', minHeight: '80px', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
                  />
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Department
                    <select value={department} onChange={e => setDepartment(e.target.value)}>
                      <option value="">Select Dept</option>
                      <option value="IT">IT</option>
                      <option value="Finance">Finance</option>
                      <option value="Operations">Operations</option>
                      <option value="HR">HR</option>
                      <option value="Marketing">Marketing</option>
                      <option value="Engineering">Engineering</option>
                    </select>
                  </label>
                  <label>
                    Business Unit
                    <input
                      type="text"
                      value={businessUnit}
                      onChange={e => setBusinessUnit(e.target.value)}
                      placeholder="e.g. Retail Bank"
                    />
                  </label>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Priority
                    <select value={priority} onChange={e => setPriority(e.target.value)}>
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </label>
                  <label>
                    Project Status
                    <select value={status} onChange={e => setStatus(e.target.value)}>
                      <option value="DRAFT">DRAFT</option>
                      <option value="IN_REVIEW">IN_REVIEW</option>
                      <option value="APPROVED">APPROVED</option>
                      <option value="REJECTED">REJECTED</option>
                      <option value="ARCHIVED">ARCHIVED</option>
                    </select>
                  </label>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Start Date
                    <input
                      type="date"
                      value={startDate}
                      onChange={e => setStartDate(e.target.value)}
                    />
                  </label>
                  <label>
                    End Date
                    <input
                      type="date"
                      value={endDate}
                      onChange={e => setEndDate(e.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Tags (comma-separated)
                  <input
                    type="text"
                    value={tags}
                    onChange={e => setTags(e.target.value)}
                    placeholder="e.g. Core Banking, Migration, Q3"
                  />
                </label>
              </div>
              <div className="modal-footer">
                <button type="button" className="admin-btn secondary" onClick={() => setIsEditOpen(false)}>Cancel</button>
                <button type="submit" className="admin-btn primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* TRANSFER MODAL */}
      {isTransferOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Transfer Project Ownership</h3>
              <button className="close-btn" onClick={() => setIsTransferOpen(false)}>×</button>
            </div>
            <form onSubmit={handleTransfer}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <p style={{ fontSize: '0.9rem', color: '#475569' }}>
                  Select the new project owner from the list of system users. 
                  The new owner will automatically be assigned the **PROJECT_MANAGER** project role.
                </p>
                <label>
                  New Project Owner *
                  <select 
                    value={newOwnerId} 
                    onChange={e => setNewOwnerId(Number(e.target.value))}
                    required
                    style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff' }}
                  >
                    <option value="">Select User</option>
                    {users.map(u => (
                      <option key={u.id} value={u.id}>
                        {u.name} ({u.email})
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="modal-footer">
                <button type="button" className="admin-btn secondary" onClick={() => setIsTransferOpen(false)}>Cancel</button>
                <button type="submit" className="admin-btn primary">Transfer Ownership</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectManagement;
