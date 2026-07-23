import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: string;
  variant: 'primary' | 'success' | 'warning' | 'danger' | 'indigo' | 'purple' | 'teal';
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, icon, variant }) => {
  return (
    <div className={`metric-card ${variant}`}>
      <div className="metric-icon-wrapper">
        <span>{icon}</span>
      </div>
      <div className="metric-details">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
      </div>
    </div>
  );
};

// Dynamic Donut Chart Component
interface DonutData {
  name: string;
  count: number;
  percentage: number;
}
const DepartmentDonutChart: React.FC<{ data: DonutData[] }> = ({ data }) => {
  const colors = ['#3b82f6', '#10b981', '#6366f1', '#a855f7', '#14b8a6', '#f59e0b', '#ef4444'];
  const bulletColors = ['blue', 'green', 'indigo', 'purple', 'teal', 'amber', 'red'];
  
  let accumulatedPercent = 0;
  const gradientSlices = data.map((dept, index) => {
    const color = colors[index % colors.length];
    const start = accumulatedPercent;
    accumulatedPercent += dept.percentage;
    const end = index === data.length - 1 ? 100 : accumulatedPercent; // snap last slice to 100%
    return `${color} ${start}% ${end}%`;
  });
  
  const conicGradientValue = gradientSlices.length > 0 
    ? `conic-gradient(${gradientSlices.join(', ')})` 
    : 'conic-gradient(#3b82f6 0% 100%)';

  return (
    <div className="donut-chart-container">
      <div className="donut-visual" style={{ background: conicGradientValue }}>
        <div className="donut-center-hole">
          <span className="donut-center-value">{data.length}</span>
          <span className="donut-center-label">Depts</span>
        </div>
      </div>
      <div className="donut-legend">
        {data.map((dept, index) => (
          <div key={dept.name} className="legend-item">
            <span className={`legend-bullet ${bulletColors[index % bulletColors.length]}`} />
            <span>{dept.name} ({dept.percentage}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
};

interface DashboardProps {
  stats: {
    totalUsers: number;
    activeUsers: number;
    totalProjects: number;
    estimatedCost: number;
    departments: DonutData[];
  };
}

const Dashboard: React.FC<DashboardProps> = ({ stats }) => {
  return (
    <div>
      <div className="admin-header-row">
        <h1>Overview Dashboard</h1>
        <p>Real-time analytics and system utilization metrics.</p>
      </div>

      <div className="metrics-grid">
        <MetricCard 
          label="Total Users" 
          value={stats.totalUsers} 
          icon="👥" 
          variant="primary" 
        />
        <MetricCard 
          label="Active Users" 
          value={stats.activeUsers} 
          icon="🟢" 
          variant="success" 
        />
        <MetricCard 
          label="Total Projects" 
          value={stats.totalProjects} 
          icon="📁" 
          variant="indigo" 
        />
        <MetricCard 
          label="Estimated Cost" 
          value={`$${stats.estimatedCost.toFixed(3)}`} 
          icon="💵" 
          variant="danger" 
        />
      </div>

      <div className="charts-grid" style={{ gridTemplateColumns: '1fr', maxWidth: '600px' }}>
        <div className="chart-card">
          <div className="chart-header">
            <h3 className="chart-title">User Distribution by Department</h3>
          </div>
          <DepartmentDonutChart data={stats.departments} />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
