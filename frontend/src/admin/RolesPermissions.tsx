import React, { useState, useEffect } from 'react';

interface RolesPermissionsProps {
  matrix: {
    [role: string]: {
      [permission: string]: boolean;
    };
  };
  loading: boolean;
  onSavePermissions: (updatedMatrix: any) => Promise<void>;
}

const RolesPermissions: React.FC<RolesPermissionsProps> = ({
  matrix,
  loading,
  onSavePermissions
}) => {
  const [localMatrix, setLocalMatrix] = useState<typeof matrix>({});
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError: boolean } | null>(null);

  // Sync state when matrix loads
  useEffect(() => {
    if (matrix && Object.keys(matrix).length > 0) {
      setLocalMatrix(JSON.parse(JSON.stringify(matrix)));
    }
  }, [matrix]);

  // List of permissions and roles
  const permissionsList = [
    { title: "Create Project", desc: "Allow creating new requirement elicitation workspace sessions" },
    { title: "Delete Project", desc: "Allow permanent removal of project workspaces and archives" },
    { title: "Edit Project", desc: "Allow manual modifications to captured structured requirements" },
    { title: "Generate Document", desc: "Allow compiling and exporting FDR documents (PDF & DOCX)" },
    { title: "Manage Users", desc: "Access user administration dashboard and modify account roles/statuses" },
    { title: "Manage Prompts", desc: "Customize or tune LLM prompts for requirements extraction" },
    { title: "Manage AI", desc: "Configure Forjinn flow parameters and prediction keys" },
    { title: "View Analytics", desc: "Inspect estimated cost, token utilization, and hours saved metrics" }
  ];

  const rolesList = ['SUPER_ADMIN', 'ADMIN', 'BUSINESS_ANALYST', 'PROJECT_MANAGER', 'VIEWER', 'REVIEWER'];

  // Toggle single permission for a role
  const handleCheckboxChange = (role: string, permission: string) => {
    setLocalMatrix((prev) => {
      const copy = { ...prev };
      if (!copy[role]) copy[role] = {};
      copy[role][permission] = !copy[role][permission];
      return copy;
    });
  };

  // Submit back to api
  const handleSave = async () => {
    setIsSaving(true);
    setStatusMessage(null);
    try {
      await onSavePermissions(localMatrix);
      setStatusMessage({ text: "Permissions matrix updated successfully!", isError: false });
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setStatusMessage({ text: err.message || "Failed to update permissions matrix.", isError: true });
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    if (window.confirm("Discard changes and reset to last saved state?")) {
      setLocalMatrix(JSON.parse(JSON.stringify(matrix)));
      setStatusMessage(null);
    }
  };

  return (
    <div>
      <div className="admin-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Roles & Permissions</h1>
          <p>Configure Role-Based Access Control (RBAC) rules mapping capabilities to system roles.</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            className="admin-btn" 
            onClick={handleReset}
            disabled={loading || isSaving}
          >
            🔄 Reset
          </button>
          <button 
            className="admin-btn primary" 
            onClick={handleSave}
            disabled={loading || isSaving || Object.keys(localMatrix).length === 0}
          >
            {isSaving ? "Saving..." : "💾 Save Changes"}
          </button>
        </div>
      </div>

      {statusMessage && (
        <div style={{
          padding: '12px 18px',
          borderRadius: '8px',
          marginBottom: '20px',
          fontSize: '0.9rem',
          fontWeight: '600',
          backgroundColor: statusMessage.isError ? '#fef2f2' : '#ecfdf5',
          color: statusMessage.isError ? '#b91c1c' : '#047857',
          border: `1px solid ${statusMessage.isError ? '#fca5a5' : '#a7f3d0'}`
        }}>
          {statusMessage.text}
        </div>
      )}

      <div className="roles-matrix-card">
        {loading ? (
          <div>
            <div className="skeleton-line" style={{ width: '40%', height: '24px', marginBottom: '24px' }} />
            <div className="skeleton-line" />
            <div className="skeleton-line" />
            <div className="skeleton-line" />
          </div>
        ) : Object.keys(localMatrix).length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon">🛡️</span>
            <h3 className="empty-state-title">No Permissions Loaded</h3>
            <p className="empty-state-desc">Authentication error or API server is unavailable.</p>
          </div>
        ) : (
          <div>
            <p className="matrix-description">
              Assign permission criteria below. Toggle the checkboxes to instantly map capabilities to defined roles.
            </p>
            <div className="matrix-table-wrapper">
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th style={{ width: '280px', textAlign: 'left' }}>System Capabilities</th>
                    {rolesList.map((role) => (
                      <th key={role} style={{ textAlign: 'center', fontSize: '0.8rem' }}>
                        {role.replace('_', ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {permissionsList.map((perm) => (
                    <tr key={perm.title}>
                      <td className="permission-info-cell">
                        <div className="permission-title">{perm.title}</div>
                        <div className="permission-desc">{perm.desc}</div>
                      </td>
                      {rolesList.map((role) => {
                        const isChecked = localMatrix[role]?.[perm.title] || false;
                        const isSuperAdmin = role === 'SUPER_ADMIN';
                        
                        return (
                          <td key={`${role}-${perm.title}`} className="matrix-checkbox-cell">
                            <input 
                              type="checkbox" 
                              className="matrix-checkbox"
                              checked={isChecked}
                              disabled={isSuperAdmin} // Super admin permissions are locked
                              onChange={() => handleCheckboxChange(role, perm.title)}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: '16px', fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic' }}>
              * Permissions for the <strong>SUPER ADMIN</strong> role are fixed and cannot be customized.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RolesPermissions;
