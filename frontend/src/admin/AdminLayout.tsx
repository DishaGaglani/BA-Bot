import React, { useState } from 'react';

interface SidebarItem {
  id: string;
  label: string;
  icon: string;
}

interface AdminLayoutProps {
  children: React.ReactNode;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentUser: any;
  onLogout: () => void;
  isSidebarCollapsed: boolean;
  setIsSidebarCollapsed: (collapsed: boolean) => void;
  onSwitchMode: () => void;
}

const AdminLayout: React.FC<AdminLayoutProps> = ({
  children,
  activeTab,
  setActiveTab,
  currentUser,
  onLogout,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  onSwitchMode
}) => {
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  const sidebarItems: SidebarItem[] = [
    { id: 'dashboard', label: 'Telemetry & Dashboard', icon: '📊' },
    { id: 'users', label: 'Access & Identity', icon: '👥' },
    { id: 'projects', label: 'Workspace Directory', icon: '📁' },
    { id: 'conversations', label: 'Dialogue & Specs', icon: '💬' },
    { id: 'settings', label: 'System Config', icon: '⚙️' }
  ];

  const getBreadcrumbTitle = (tab: string) => {
    const item = sidebarItems.find(i => i.id === tab);
    return item ? item.label : 'Dashboard';
  };

  const getInitials = (name: string) => {
    if (!name) return 'A';
    return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  };

  return (
    <div className="admin-portal-wrapper">
      {/* SIDEBAR NAVIGATION */}
      <aside className={`admin-sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <h2>🤖 BA-Bot Portal</h2>
          <button 
            className="collapse-btn" 
            title={isSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          >
            {isSidebarCollapsed ? '▶' : '◀'}
          </button>
        </div>

        <ul className="sidebar-menu">
          {sidebarItems.map((item) => (
            <li key={item.id} className="sidebar-item">
              <a 
                className={`sidebar-link ${activeTab === item.id ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
              >
                <span className="sidebar-icon">{item.icon}</span>
                <span className="sidebar-text">{item.label}</span>
              </a>
            </li>
          ))}
        </ul>

        <div className="sidebar-footer">
          <button 
            className="admin-btn primary small" 
            style={{ width: '100%' }}
            onClick={onSwitchMode}
          >
            🧑‍💼 Switch Mode
          </button>
        </div>
      </aside>

      {/* MAIN CONTAINER */}
      <div className="admin-main-container">
        {/* HEADER BAR */}
        <header className="admin-header">
          <div className="header-left">
            <div className="admin-breadcrumbs">
              <span className="breadcrumb-item">Admin</span>
              <span className="breadcrumb-separator">/</span>
              <span className="breadcrumb-item active">{getBreadcrumbTitle(activeTab)}</span>
            </div>
          </div>

          <div className="header-right">
            {/* Notifications Area */}
            <button className="notification-bell-btn" title="View Notifications">
              🔔
              <span className="notification-badge" />
            </button>

            {/* Profile Dropdown */}
            <div className="profile-dropdown-container">
              <button 
                className="profile-dropdown-trigger"
                onClick={() => setIsProfileOpen(!isProfileOpen)}
              >
                <div className="avatar-placeholder">
                  {getInitials(currentUser?.name)}
                </div>
                <div className="trigger-info">
                  <span className="trigger-name">{currentUser?.name}</span>
                  <span className="trigger-role">{currentUser?.role}</span>
                </div>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>▼</span>
              </button>

              {isProfileOpen && (
                <>
                  <div 
                    style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 140 }} 
                    onClick={() => setIsProfileOpen(false)} 
                  />
                  <div className="profile-menu-dropdown">
                    <div className="dropdown-user-details">
                      <div style={{ fontWeight: '600', fontSize: '0.85rem' }}>{currentUser?.name}</div>
                      <div className="dropdown-user-email">{currentUser?.email}</div>
                    </div>
                    <button 
                      className="dropdown-item" 
                      onClick={() => {
                        setIsProfileOpen(false);
                        onSwitchMode();
                      }}
                    >
                      🧑‍💼 Switch to BA Mode
                    </button>
                    <button 
                      className="dropdown-item logout" 
                      onClick={() => {
                        setIsProfileOpen(false);
                        onLogout();
                      }}
                    >
                      🚪 Sign Out
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* PAGE CONTENT */}
        <main className="admin-content">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AdminLayout;
