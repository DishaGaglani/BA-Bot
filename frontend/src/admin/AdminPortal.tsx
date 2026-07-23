import React, { useState, useEffect } from 'react';
import AdminLayout from './AdminLayout';
import Dashboard from './Dashboard';
import UserManagement, { User } from './UserManagement';
import RolesPermissions from './RolesPermissions';
import ProjectManagement from './ProjectManagement';
import ProjectDetails from './ProjectDetails';
import ConversationsPanel from './ConversationsPanel';
import DocumentsPanel from './DocumentsPanel';
import AnalyticsPanel from './AnalyticsPanel';
import SettingsPanel from './SettingsPanel';
import './Admin.css';

interface AdminPortalProps {
  token: string;
  currentUser: any;
  onLogout: () => void;
  onSwitchMode: () => void;
  projectsCount: number;
}

const AdminPortal: React.FC<AdminPortalProps> = ({
  token,
  currentUser,
  onLogout,
  onSwitchMode,
  projectsCount
}) => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [usersList, setUsersList] = useState<User[]>([]);
  
  // Sub-tab selectors for consolidated views
  const [dashboardSubTab, setDashboardSubTab] = useState<'metrics' | 'analytics'>('metrics');
  const [usersSubTab, setUsersSubTab] = useState<'directory' | 'permissions'>('directory');
  const [conversationsSubTab, setConversationsSubTab] = useState<'dialogue' | 'specs'>('dialogue');
  const [logsList, setLogsList] = useState<any[]>([]);
  const [permissionsMatrix, setPermissionsMatrix] = useState<any>({});
  const [dashboardStats, setDashboardStats] = useState<any>({
    totalUsers: 0,
    activeUsers: 0,
    totalProjects: 0,
    documentsGenerated: 0,
    aiRequestsToday: 0,
    tokenUsage: 0,
    estimatedCost: 0,
    activity: [],
    departments: []
  });

  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [loadingPermissions, setLoadingPermissions] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);

  // Fetch users
  const fetchUsers = async () => {
    setLoadingUsers(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/users', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUsersList(data);
      }
    } catch (err) {
      console.error('Failed to load users', err);
    } finally {
      setLoadingUsers(false);
    }
  };

  // Fetch logs
  const fetchLogs = async () => {
    setLoadingLogs(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/audit-logs', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setLogsList(data);
      }
    } catch (err) {
      console.error('Failed to load audit logs', err);
    } finally {
      setLoadingLogs(false);
    }
  };

  // Fetch permissions
  const fetchPermissions = async () => {
    setLoadingPermissions(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/permissions', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPermissionsMatrix(data);
      }
    } catch (err) {
      console.error('Failed to load permissions matrix', err);
    } finally {
      setLoadingPermissions(false);
    }
  };

  // Fetch dashboard stats
  const fetchDashboardStats = async () => {
    setLoadingStats(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/dashboard-stats', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDashboardStats(data);
      }
    } catch (err) {
      console.error('Failed to load dashboard stats', err);
    } finally {
      setLoadingStats(false);
    }
  };

  // Load initial data
  useEffect(() => {
    void fetchUsers();
    void fetchLogs();
    void fetchPermissions();
    void fetchDashboardStats();
  }, [token]);

  // Reset selected project when active tab changes
  useEffect(() => {
    setSelectedProjectId(null);
  }, [activeTab]);

  // Actions
  const handleUpdateRole = async (userId: number, role: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/users/${userId}/role`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ role })
      });
      if (res.ok) {
        await fetchUsers();
        await fetchLogs();
        await fetchDashboardStats();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to update user role.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating user role.');
    }
  };

  const handleUpdateUser = async (userId: number, data: { name: string; email: string; role: string; department: string; status: string }) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      });
      if (res.ok) {
        await fetchUsers();
        await fetchLogs();
        await fetchDashboardStats();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to update user details.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating user details.');
    }
  };

  const handleDeleteUser = async (userId: number) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/users/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchUsers();
        await fetchLogs();
        await fetchDashboardStats();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to delete user.');
      }
    } catch (err) {
      console.error(err);
      alert('Error deleting user.');
    }
  };

  const handleAddUser = async (data: any) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      });
      if (res.ok) {
        await fetchUsers();
        await fetchLogs();
        await fetchDashboardStats();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to create user account.');
      }
    } catch (err) {
      console.error(err);
      alert('Error creating user account.');
    }
  };

  const handleSavePermissions = async (updatedMatrix: any) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/permissions', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(updatedMatrix)
      });
      if (res.ok) {
        setPermissionsMatrix(updatedMatrix);
        await fetchLogs();
        await fetchDashboardStats();
      } else {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to save permissions.');
      }
    } catch (err) {
      console.error(err);
      throw err;
    }
  };

  return (
    <AdminLayout
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      currentUser={currentUser}
      onLogout={onLogout}
      isSidebarCollapsed={isSidebarCollapsed}
      setIsSidebarCollapsed={setIsSidebarCollapsed}
      onSwitchMode={onSwitchMode}
    >
      {activeTab === 'dashboard' && (
        <>
          <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: '20px', gap: '20px' }}>
            <button 
              onClick={() => setDashboardSubTab('metrics')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: dashboardSubTab === 'metrics' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: dashboardSubTab === 'metrics' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              📊 Overview Metrics
            </button>
            <button 
              onClick={() => setDashboardSubTab('analytics')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: dashboardSubTab === 'analytics' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: dashboardSubTab === 'analytics' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              📈 Telemetry & Analytics
            </button>
          </div>
          {dashboardSubTab === 'metrics' ? (
            <Dashboard stats={dashboardStats} />
          ) : (
            <AnalyticsPanel token={token} />
          )}
        </>
      )}
      
      {activeTab === 'users' && (
        <>
          <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: '20px', gap: '20px' }}>
            <button 
              onClick={() => setUsersSubTab('directory')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: usersSubTab === 'directory' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: usersSubTab === 'directory' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              👥 User Directory
            </button>
            <button 
              onClick={() => setUsersSubTab('permissions')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: usersSubTab === 'permissions' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: usersSubTab === 'permissions' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              🛡️ RBAC Permissions Matrix
            </button>
          </div>
          {usersSubTab === 'directory' ? (
            <UserManagement
              users={usersList}
              currentUser={currentUser}
              loading={loadingUsers}
              onUpdateRole={handleUpdateRole}
              onUpdateUser={handleUpdateUser}
              onDeleteUser={handleDeleteUser}
              onAddUser={handleAddUser}
            />
          ) : (
            <RolesPermissions
              matrix={permissionsMatrix}
              loading={loadingPermissions}
              onSavePermissions={handleSavePermissions}
            />
          )}
        </>
      )}

      {activeTab === 'projects' && (
        selectedProjectId !== null ? (
          <ProjectDetails 
            token={token} 
            projectId={selectedProjectId} 
            onBack={() => setSelectedProjectId(null)} 
            users={usersList}
          />
        ) : (
          <ProjectManagement 
            token={token} 
            onSelectProject={setSelectedProjectId} 
            users={usersList}
          />
        )
      )}

      {activeTab === 'conversations' && (
        <>
          <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', marginBottom: '20px', gap: '20px' }}>
            <button 
              onClick={() => setConversationsSubTab('dialogue')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: conversationsSubTab === 'dialogue' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: conversationsSubTab === 'dialogue' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              💬 Chat Dialogue Monitoring
            </button>
            <button 
              onClick={() => setConversationsSubTab('specs')}
              style={{
                padding: '10px 4px',
                background: 'none',
                border: 'none',
                borderBottom: conversationsSubTab === 'specs' ? '2px solid var(--admin-primary)' : '2px solid transparent',
                color: conversationsSubTab === 'specs' ? 'var(--admin-primary)' : '#64748b',
                fontWeight: '600',
                fontSize: '0.9rem',
                cursor: 'pointer',
                marginBottom: '-1px'
              }}
            >
              📄 Compliance Documents
            </button>
          </div>
          {conversationsSubTab === 'dialogue' ? (
            <ConversationsPanel token={token} />
          ) : (
            <DocumentsPanel token={token} />
          )}
        </>
      )}

      {activeTab === 'settings' && (
        <SettingsPanel token={token} />
      )}

      {/* Placeholder Tabs */}
      {!['dashboard', 'users', 'projects', 'conversations', 'settings'].includes(activeTab) && (
        <div style={{ padding: '24px', backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', minHeight: '300px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', marginBottom: '16px' }}>🚧</div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: '700', color: '#0f172a', margin: '0 0 8px 0' }}>Under Construction</h2>
          <p style={{ color: '#64748b', maxWidth: '360px', fontSize: '0.95rem', margin: '0' }}>
            The administrative console for <strong>{activeTab.toUpperCase()}</strong> is being established as part of the next portal release phase.
          </p>
        </div>
      )}
    </AdminLayout>
  );
};

export default AdminPortal;
