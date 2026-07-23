import React, { useState, useMemo } from 'react';

export interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  department: string;
  status: string;
  projects_count: number;
  last_login: string | null;
  created_at: string | null;
}

interface UserManagementProps {
  users: User[];
  currentUser: any;
  loading: boolean;
  onUpdateRole: (userId: number, role: string) => Promise<void>;
  onUpdateUser: (userId: number, data: { name: string; email: string; role: string; department: string; status: string }) => Promise<void>;
  onDeleteUser: (userId: number) => Promise<void>;
  onAddUser: (data: any) => Promise<void>;
}

const UserManagement: React.FC<UserManagementProps> = ({
  users,
  currentUser,
  loading,
  onUpdateRole,
  onUpdateUser,
  onDeleteUser,
  onAddUser
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('ALL');
  const [deptFilter, setDeptFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  // Modal states
  const [viewUser, setViewUser] = useState<User | null>(null);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [isAddOpen, setIsAddOpen] = useState(false);

  // Form states
  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editRole, setEditRole] = useState('');
  const [editDept, setEditDept] = useState('');
  const [editStatus, setEditStatus] = useState('');

  const [addName, setAddName] = useState('');
  const [addEmail, setAddEmail] = useState('');
  const [addPassword, setAddPassword] = useState('');
  const [addRole, setAddRole] = useState('BUSINESS_ANALYST');
  const [addDept, setAddDept] = useState('IT');

  // Available options
  const ROLES = ['SUPER_ADMIN', 'ADMIN', 'BUSINESS_ANALYST', 'PROJECT_MANAGER', 'VIEWER', 'REVIEWER'];
  const DEPARTMENTS = ['IT', 'Product', 'Business Analysis', 'Finance', 'HR', 'Operations'];

  // Handle Edit click
  const handleStartEdit = (u: User) => {
    setEditUser(u);
    setEditName(u.name);
    setEditEmail(u.email);
    setEditRole(u.role);
    setEditDept(u.department || 'IT');
    setEditStatus(u.status || 'ACTIVE');
  };

  // Submit edits
  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editUser) return;
    try {
      await onUpdateUser(editUser.id, {
        name: editName,
        email: editEmail,
        role: editRole,
        department: editDept,
        status: editStatus
      });
      setEditUser(null);
    } catch (err) {
      console.error(err);
    }
  };

  // Submit new user
  const handleSaveAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await onAddUser({
        name: addName,
        email: addEmail,
        password: addPassword,
        role: addRole,
        department: addDept
      });
      setIsAddOpen(false);
      setAddName('');
      setAddEmail('');
      setAddPassword('');
      setAddRole('BUSINESS_ANALYST');
      setAddDept('IT');
    } catch (err) {
      console.error(err);
    }
  };

  // Toggle status directly
  const handleToggleStatus = async (u: User) => {
    const nextStatus = u.status === 'DISABLED' ? 'ACTIVE' : 'DISABLED';
    try {
      await onUpdateUser(u.id, {
        name: u.name,
        email: u.email,
        role: u.role,
        department: u.department || 'IT',
        status: nextStatus
      });
    } catch (err) {
      console.error(err);
    }
  };

  // Filter and Search logic
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const matchSearch = 
        u.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (u.department && u.department.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchRole = roleFilter === 'ALL' || u.role === roleFilter;
      const matchDept = deptFilter === 'ALL' || u.department === deptFilter;
      const matchStatus = statusFilter === 'ALL' || u.status === statusFilter;

      return matchSearch && matchRole && matchDept && matchStatus;
    });
  }, [users, searchTerm, roleFilter, deptFilter, statusFilter]);

  // Pagination logic
  const totalPages = Math.ceil(filteredUsers.length / itemsPerPage) || 1;
  const paginatedUsers = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredUsers.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredUsers, currentPage]);

  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  const getRoleBadgeClass = (r: string) => {
    switch (r) {
      case 'SUPER_ADMIN': return 'badge danger';
      case 'ADMIN': return 'badge danger';
      case 'BUSINESS_ANALYST': return 'badge primary';
      case 'PROJECT_MANAGER': return 'badge indigo';
      case 'VIEWER': return 'badge secondary';
      case 'REVIEWER': return 'badge warning';
      default: return 'badge secondary';
    }
  };

  return (
    <div>
      <div className="admin-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>User Management</h1>
          <p>Create, update, assign roles and manage administrative states of users.</p>
        </div>
        <button className="admin-btn primary" onClick={() => setIsAddOpen(true)}>
          ➕ Add New User
        </button>
      </div>

      <div className="admin-table-panel">
        {/* Toolbar search & filters */}
        <div className="table-toolbar">
          <div className="toolbar-left">
            <div className="search-input-wrapper">
              <span className="search-icon-svg">🔍</span>
              <input 
                type="text" 
                className="search-input" 
                placeholder="Search by name, email..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
              />
            </div>
            
            <select 
              className="filter-select"
              value={roleFilter}
              onChange={(e) => {
                setRoleFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="ALL">All Roles</option>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>

            <select 
              className="filter-select"
              value={deptFilter}
              onChange={(e) => {
                setDeptFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="ALL">All Departments</option>
              {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>

            <select 
              className="filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="DISABLED">Disabled</option>
            </select>
          </div>
        </div>

        {/* Loading Skeletons */}
        {loading ? (
          <div style={{ padding: '24px' }}>
            <div className="skeleton-table-row">
              <div className="skeleton-table-cell" style={{ flex: 1.5 }}><div className="skeleton-line" /></div>
              <div className="skeleton-table-cell" style={{ flex: 2 }}><div className="skeleton-line" /></div>
              <div className="skeleton-table-cell"><div className="skeleton-line" /></div>
              <div className="skeleton-table-cell"><div className="skeleton-line" /></div>
              <div className="skeleton-table-cell"><div className="skeleton-line" /></div>
              <div className="skeleton-table-cell"><div className="skeleton-line" /></div>
            </div>
            {[1, 2, 3].map((n) => (
              <div key={n} className="skeleton-table-row">
                <div className="skeleton-table-cell" style={{ flex: 1.5 }}><div className="skeleton-line" style={{ width: '80%' }} /></div>
                <div className="skeleton-table-cell" style={{ flex: 2 }}><div className="skeleton-line" style={{ width: '90%' }} /></div>
                <div className="skeleton-table-cell"><div className="skeleton-line" style={{ width: '60%' }} /></div>
                <div className="skeleton-table-cell"><div className="skeleton-line" style={{ width: '70%' }} /></div>
                <div className="skeleton-table-cell"><div className="skeleton-line" style={{ width: '50%' }} /></div>
                <div className="skeleton-table-cell"><div className="skeleton-line" style={{ width: '40%' }} /></div>
              </div>
            ))}
          </div>
        ) : filteredUsers.length === 0 ? (
          /* Empty State */
          <div className="empty-state">
            <span className="empty-state-icon">👥</span>
            <h3 className="empty-state-title">No Users Found</h3>
            <p className="empty-state-desc">Try clearing filters or adjusting search queries to display users.</p>
          </div>
        ) : (
          /* Table */
          <div className="table-responsive-wrapper">
            <table className="admin-data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Department</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Projects</th>
                  <th>Last Login</th>
                  <th style={{ textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paginatedUsers.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: '600' }}>{u.name}</td>
                    <td style={{ color: '#475569' }}>{u.email}</td>
                    <td>{u.department || 'IT'}</td>
                    <td>
                      <span className={getRoleBadgeClass(u.role)}>{u.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${u.status === 'DISABLED' ? 'danger' : 'success'}`}>
                        {u.status || 'ACTIVE'}
                      </span>
                    </td>
                    <td style={{ fontWeight: '600' }}>{u.projects_count}</td>
                    <td style={{ color: '#64748b', fontSize: '0.85rem' }}>
                      {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div className="action-buttons-cell" style={{ justifyContent: 'center' }}>
                        <button 
                          className="icon-action-btn" 
                          title="View Details"
                          onClick={() => setViewUser(u)}
                        >
                          👁️
                        </button>
                        <button 
                          className="icon-action-btn edit" 
                          title="Edit Details"
                          onClick={() => handleStartEdit(u)}
                        >
                          ✏️
                        </button>
                        {u.id !== currentUser?.id && (
                          <>
                            <button 
                              className={`icon-action-btn disable ${u.status === 'DISABLED' ? 'success' : 'warning'}`}
                              title={u.status === 'DISABLED' ? 'Enable Account' : 'Disable Account'}
                              onClick={() => handleToggleStatus(u)}
                            >
                              {u.status === 'DISABLED' ? '✅' : '🚫'}
                            </button>
                            <button 
                              className="icon-action-btn delete" 
                              title="Delete User"
                              onClick={() => {
                                if (window.confirm(`Are you sure you want to permanently delete user ${u.name}?`)) {
                                  void onDeleteUser(u.id);
                                }
                              }}
                            >
                              🗑️
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer Pagination */}
        {!loading && filteredUsers.length > 0 && (
          <div className="table-footer">
            <span className="table-stats">
              Showing {(currentPage - 1) * itemsPerPage + 1} to {Math.min(currentPage * itemsPerPage, filteredUsers.length)} of {filteredUsers.length} entries
            </span>
            <div className="pagination-controls">
              <button 
                className="pagination-btn"
                disabled={currentPage === 1}
                onClick={() => handlePageChange(currentPage - 1)}
              >
                Previous
              </button>
              {Array.from({ length: totalPages }, (_, i) => (
                <button 
                  key={i + 1} 
                  className={`pagination-btn ${currentPage === i + 1 ? 'active' : ''}`}
                  onClick={() => handlePageChange(i + 1)}
                >
                  {i + 1}
                </button>
              ))}
              <button 
                className="pagination-btn"
                disabled={currentPage === totalPages}
                onClick={() => handlePageChange(currentPage + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* VIEW MODAL */}
      {viewUser && (
        <div className="admin-modal-overlay" onClick={() => setViewUser(null)}>
          <div className="admin-modal-container" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">User Details</h3>
              <button className="modal-close-btn" onClick={() => setViewUser(null)}>×</button>
            </div>
            <div className="modal-body">
              <div className="modal-detail-row">
                <span className="detail-label">User ID</span>
                <span className="detail-value">{viewUser.id}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Name</span>
                <span className="detail-value">{viewUser.name}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Email</span>
                <span className="detail-value">{viewUser.email}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Department</span>
                <span className="detail-value">{viewUser.department || 'IT'}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">System Role</span>
                <span className="detail-value">{viewUser.role}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Account Status</span>
                <span className="detail-value">{viewUser.status || 'ACTIVE'}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Created At</span>
                <span className="detail-value">{viewUser.created_at ? new Date(viewUser.created_at).toLocaleString() : 'N/A'}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Last Login</span>
                <span className="detail-value">{viewUser.last_login ? new Date(viewUser.last_login).toLocaleString() : 'Never'}</span>
              </div>
              <div className="modal-detail-row">
                <span className="detail-label">Active Projects</span>
                <span className="detail-value">{viewUser.projects_count}</span>
              </div>
            </div>
            <div className="modal-footer">
              <button className="admin-btn" onClick={() => setViewUser(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editUser && (
        <div className="admin-modal-overlay" onClick={() => setEditUser(null)}>
          <div className="admin-modal-container" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={handleSaveEdit}>
              <div className="modal-header">
                <h3 className="modal-title">Edit User Details</h3>
                <button className="modal-close-btn" type="button" onClick={() => setEditUser(null)}>×</button>
              </div>
              <div className="modal-body">
                <div className="admin-form-group">
                  <label>Full Name</label>
                  <input 
                    type="text" 
                    className="admin-form-input" 
                    required 
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>
                <div className="admin-form-group">
                  <label>Email Address</label>
                  <input 
                    type="email" 
                    className="admin-form-input" 
                    required 
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                  />
                </div>
                <div className="admin-form-group">
                  <label>Department</label>
                  <select 
                    className="admin-form-input" 
                    value={editDept}
                    onChange={(e) => setEditDept(e.target.value)}
                  >
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div className="admin-form-group">
                  <label>System Role</label>
                  <select 
                    className="admin-form-input" 
                    value={editRole}
                    disabled={editUser.id === currentUser?.id}
                    onChange={(e) => setEditRole(e.target.value)}
                  >
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div className="admin-form-group">
                  <label>Account Status</label>
                  <select 
                    className="admin-form-input" 
                    value={editStatus}
                    disabled={editUser.id === currentUser?.id}
                    onChange={(e) => setEditStatus(e.target.value)}
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="DISABLED">DISABLED</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button className="admin-btn" type="button" onClick={() => setEditUser(null)}>Cancel</button>
                <button className="admin-btn primary" type="submit">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ADD USER MODAL */}
      {isAddOpen && (
        <div className="admin-modal-overlay" onClick={() => setIsAddOpen(false)}>
          <div className="admin-modal-container" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={handleSaveAdd}>
              <div className="modal-header">
                <h3 className="modal-title">Add New User</h3>
                <button className="modal-close-btn" type="button" onClick={() => setIsAddOpen(false)}>×</button>
              </div>
              <div className="modal-body">
                <div className="admin-form-group">
                  <label>Full Name</label>
                  <input 
                    type="text" 
                    className="admin-form-input" 
                    placeholder="John Doe"
                    required 
                    value={addName}
                    onChange={(e) => setAddName(e.target.value)}
                  />
                </div>
                <div className="admin-form-group">
                  <label>Email Address</label>
                  <input 
                    type="email" 
                    className="admin-form-input" 
                    placeholder="john@example.com"
                    required 
                    value={addEmail}
                    onChange={(e) => setAddEmail(e.target.value)}
                  />
                </div>
                <div className="admin-form-group">
                  <label>Password</label>
                  <input 
                    type="password" 
                    className="admin-form-input" 
                    placeholder="••••••••"
                    required 
                    value={addPassword}
                    onChange={(e) => setAddPassword(e.target.value)}
                  />
                </div>
                <div className="admin-form-group">
                  <label>Department</label>
                  <select 
                    className="admin-form-input" 
                    value={addDept}
                    onChange={(e) => setAddDept(e.target.value)}
                  >
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div className="admin-form-group">
                  <label>System Role</label>
                  <select 
                    className="admin-form-input" 
                    value={addRole}
                    onChange={(e) => setAddRole(e.target.value)}
                  >
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button className="admin-btn" type="button" onClick={() => setIsAddOpen(false)}>Cancel</button>
                <button className="admin-btn primary" type="submit">Create User</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagement;
