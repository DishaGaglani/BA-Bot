import React, { useState, useEffect } from 'react';

interface RoleDistribution {
  role: string;
  count: number;
}

interface ProjectsTrend {
  date: string;
  count: number;
}

interface ActiveUser {
  name: string;
  email: string;
  activity_count: number;
}

interface ActionSummary {
  action: string;
  count: number;
}

interface AnalyticsState {
  rolesDistribution: RoleDistribution[];
  projectsTrend: ProjectsTrend[];
  mostActiveUsers: ActiveUser[];
  actionsSummary: ActionSummary[];
}

interface AnalyticsPanelProps {
  token: string;
}

const AnalyticsPanel: React.FC<AnalyticsPanelProps> = ({ token }) => {
  const [data, setData] = useState<AnalyticsState | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/analytics', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const payload = await res.json();
        setData(payload);
      }
    } catch (err) {
      console.error('Failed to load analytics data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchAnalytics();
  }, [token]);

  if (loading) {
    return (
      <div style={{ padding: '20px' }}>
        <h1>System Analytics</h1>
        <div className="skeleton-container" style={{ marginTop: '20px' }}>
          <div className="skeleton-row" style={{ height: '200px' }} />
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <h1>System Analytics</h1>
        <p style={{ color: '#64748b' }}>Analytics details could not be compiled.</p>
      </div>
    );
  }

  const { rolesDistribution, projectsTrend, mostActiveUsers, actionsSummary } = data;

  const totalUsers = rolesDistribution.reduce((acc, r) => acc + r.count, 0);
  const totalProjects = projectsTrend.reduce((acc, p) => acc + p.count, 0);

  // Maximum value for CSS trend height scaling
  const maxProjectCount = projectsTrend.length > 0 ? Math.max(...projectsTrend.map(p => p.count)) : 1;

  return (
    <div>
      <div className="admin-header-row">
        <h1>System Analytics</h1>
        <p>Aggregate platform transaction trends, user roles, and operation distribution summaries.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px', marginTop: '20px' }}>
        
        {/* USERS BY ROLE */}
        <div className="table-card" style={{ padding: '24px' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Users by System Role</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {rolesDistribution.map(r => {
              const percentage = totalUsers > 0 ? Math.round((r.count / totalUsers) * 100) : 0;
              return (
                <div key={r.role}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: '600', marginBottom: '6px', color: '#334155' }}>
                    <span style={{ textTransform: 'capitalize' }}>{r.role.toLowerCase()}</span>
                    <span>{r.count} users ({percentage}%)</span>
                  </div>
                  <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                    <div style={{
                      width: `${percentage}%`,
                      height: '100%',
                      background: r.role === 'SUPER_ADMIN' || r.role === 'ADMIN' ? 'var(--admin-primary)' : '#64748b',
                      borderRadius: '4px'
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* TOP USERS ACTIVITY */}
        <div className="table-card" style={{ padding: '24px' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Top Operators (Activity Logs)</h3>
          {mostActiveUsers.length === 0 ? (
            <p style={{ color: '#64748b', fontSize: '0.9rem', textAlign: 'center', padding: '20px 0' }}>
              No system user transactions logged yet.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {mostActiveUsers.map((u, idx) => (
                <div key={u.email} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: idx < mostActiveUsers.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                  <div>
                    <div style={{ fontWeight: '600', color: '#0f172a', fontSize: '0.9rem' }}>{u.name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{u.email}</div>
                  </div>
                  <span style={{
                    fontSize: '0.8rem',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    background: '#e0f2fe',
                    color: '#0369a1',
                    fontWeight: 'bold'
                  }}>
                    {u.activity_count} Logs
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>

      {/* PROJECTS GROWTH TREND */}
      <div className="table-card" style={{ padding: '24px', marginTop: '20px' }}>
        <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Projects Registration Trend (Timeline)</h3>
        {projectsTrend.length === 0 ? (
          <p style={{ color: '#64748b', fontSize: '0.9rem', textAlign: 'center', padding: '40px 0' }}>
            No project registration logs available.
          </p>
        ) : (
          <div>
            <div style={{ display: 'flex', alignItems: 'flex-end', height: '180px', gap: '12px', borderBottom: '2px solid #e2e8f0', paddingBottom: '8px', overflowX: 'auto' }}>
              {projectsTrend.map(p => {
                const heightPercentage = Math.max(10, Math.round((p.count / maxProjectCount) * 100));
                return (
                  <div key={p.date} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: '1', minWidth: '40px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--admin-primary)', marginBottom: '4px' }}>
                      {p.count}
                    </span>
                    <div style={{
                      width: '100%',
                      height: `${heightPercentage}px`,
                      background: 'linear-gradient(to top, var(--admin-primary), #3b82f6)',
                      borderRadius: '4px 4px 0 0',
                      transition: 'height 0.3s ease'
                    }} />
                    <span style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '8px', whiteSpace: 'nowrap' }}>
                      {new Date(p.date).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: '12px', fontSize: '0.8rem', color: '#64748b', textAlign: 'right' }}>
              Total Projects Created: <strong>{totalProjects}</strong>
            </div>
          </div>
        )}
      </div>

      {/* MOST EXECUTED ACTIONS */}
      <div className="table-card" style={{ padding: '24px', marginTop: '20px' }}>
        <h3 style={{ margin: '0 0 16px 0', fontSize: '1.05rem', color: '#0f172a' }}>Transaction Distributions (Actions Summary)</h3>
        {actionsSummary.length === 0 ? (
          <p style={{ color: '#64748b', fontSize: '0.9rem', textAlign: 'center', padding: '20px 0' }}>
            No operations captured in audit logs.
          </p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '12px' }}>
            {actionsSummary.map(a => (
              <div key={a.action} style={{ background: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: '600', color: '#334155', textTransform: 'capitalize' }}>
                  {a.action}
                </span>
                <span style={{
                  fontSize: '0.8rem',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: '#f1f5f9',
                  color: '#475569',
                  fontWeight: 'bold'
                }}>
                  {a.count}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
};

export default AnalyticsPanel;
