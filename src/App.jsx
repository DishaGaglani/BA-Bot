import { useState } from 'react'
import './App.css'

const initialProject = {
  project: {
    name: 'Retail Inventory AI',
    department: 'Operations',
    sponsor: 'John Doe',
  },
  overview: {
    description: 'AI system for inventory forecasting and replenishment across retail stores.',
    stakeholders: ['Store Managers', 'Warehouse Staff', 'Finance Lead'],
  },
  discovery: {
    business_problem: 'Store teams struggle to forecast demand and prevent stockouts.',
    business_goals: 'Reduce stockouts, improve service levels, and save planner time.',
    desired_outcomes: 'Faster replenishment and better inventory visibility.',
    constraints: 'Must integrate with current ERP and support offline use in stores.',
  },
  functional_requirements: [
    { title: 'Barcode Scanning', priority: 'High', confidence: 0.96 },
    { title: 'Demand Forecasting', priority: 'High', confidence: 0.91 },
    { title: 'Reorder Recommendations', priority: 'Medium', confidence: 0.88 },
  ],
  missing_fields: ['KPIs', 'ERP Integration', 'Security Review'],
  next_question: 'What ERP system do you currently use?',
}

const initialMessages = [
  { role: 'ai', text: 'Hello. Tell me about your project and the business problem you want to solve.' },
  { role: 'user', text: 'We need a retail inventory solution for our stores and warehouse planning.' },
  { role: 'ai', text: 'Great. I will capture the business goals, stakeholders, and the core requirements for the workflow.' },
]

const navItems = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'new-project', label: 'New Project' },
  { id: 'interview', label: 'Interview Workspace' },
  { id: 'review', label: 'Review' },
  { id: 'export', label: 'Export' },
]

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [projectData, setProjectData] = useState(initialProject)
  const [messages, setMessages] = useState(initialMessages)
  const [draftInput, setDraftInput] = useState('')
  const [notice, setNotice] = useState(null)

  const completion = Math.round(
    (Number(Boolean(projectData.project.name)) +
      Number(Boolean(projectData.overview.description)) +
      Number(Boolean(projectData.discovery.business_problem)) +
      Number(Boolean(projectData.discovery.business_goals)) +
      Number(projectData.functional_requirements.length > 0)) /
      5 *
      100,
  )

  const progressItems = [
    { label: 'Overview', complete: Boolean(projectData.overview.description) },
    { label: 'Discovery', complete: Boolean(projectData.discovery.business_problem) },
    { label: 'Business', complete: Boolean(projectData.discovery.business_goals) },
    { label: 'Functional', complete: projectData.functional_requirements.length > 0 },
    { label: 'NFR', complete: Boolean(projectData.discovery.constraints) },
    { label: 'Approval', complete: projectData.missing_fields.length < 2 },
  ]

  const handleSend = (event) => {
    event.preventDefault()
    if (!draftInput.trim()) return

    const incoming = draftInput.trim()
    const lower = incoming.toLowerCase()

    setMessages((prev) => [...prev, { role: 'user', text: incoming }])

    const response = lower.includes('erp')
      ? 'I will capture the ERP dependency and flag it in the missing information panel.'
      : 'I have captured that input and I will keep advancing the discovery flow.'

    if (lower.includes('kpi') || lower.includes('requirement')) {
      setNotice({ title: 'Requirement Added', detail: 'Business goal captured with confidence' })
      setTimeout(() => setNotice(null), 1800)
    }

    setMessages((prev) => [...prev, { role: 'ai', text: response }])
    setDraftInput('')
  }

  const updateField = (section, key, value) => {
    setProjectData((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }))
  }

  const renderDashboard = () => (
    <div className="page-grid">
      <section className="page hero-card">
        <div>
          <p className="eyebrow">Business Analyst AI</p>
          <h1>Turn interviews into structured requirement discovery.</h1>
          <p className="muted">
            Guide conversations, keep the live form aligned, and move every project into a review-ready document.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary" onClick={() => setActivePage('interview')}>
            Open Interview Workspace
          </button>
          <button className="secondary" onClick={() => setActivePage('new-project')}>
            Create New Project
          </button>
        </div>
      </section>

      <section className="page">
        <div className="section-heading">
          <h2>New Project</h2>
          <button className="link" onClick={() => setActivePage('new-project')}>
            Open
          </button>
        </div>
        <div className="card-grid">
          <article className="mini-card">
            <h3>Project Name</h3>
            <p>{projectData.project.name}</p>
          </article>
          <article className="mini-card">
            <h3>Department</h3>
            <p>{projectData.project.department}</p>
          </article>
          <article className="mini-card">
            <h3>Sponsor</h3>
            <p>{projectData.project.sponsor}</p>
          </article>
        </div>
      </section>

      <section className="page">
        <div className="section-heading">
          <h2>Recent Projects</h2>
          <span className="badge">4 active</span>
        </div>
        <div className="list-stack">
          <div className="list-row">
            <div>
              <strong>AI HR Assistant</strong>
              <p className="muted">85% complete</p>
            </div>
            <button className="secondary">Continue</button>
          </div>
          <div className="list-row">
            <div>
              <strong>Retail Automation</strong>
              <p className="muted">Completed</p>
            </div>
            <span className="badge success">Done</span>
          </div>
          <div className="list-row">
            <div>
              <strong>Tender Analyzer</strong>
              <p className="muted">Draft</p>
            </div>
            <span className="badge">Draft</span>
          </div>
        </div>
      </section>

      <section className="page">
        <div className="section-heading">
          <h2>Analytics</h2>
        </div>
        <div className="stats-grid">
          <article className="stat-card">
            <span className="stat-label">Projects</span>
            <strong>24</strong>
          </article>
          <article className="stat-card">
            <span className="stat-label">Completed</span>
            <strong>16</strong>
          </article>
          <article className="stat-card">
            <span className="stat-label">Pending</span>
            <strong>8</strong>
          </article>
          <article className="stat-card">
            <span className="stat-label">Hours Saved</span>
            <strong>142</strong>
          </article>
        </div>
      </section>
    </div>
  )

  const renderNewProject = () => (
    <div className="page centered-page">
      <section className="page form-card">
        <div className="section-heading">
          <h2>Create Project</h2>
          <span className="badge">Small intake form</span>
        </div>
        <div className="form-grid">
          <label>
            Project Name
            <input
              value={projectData.project.name}
              onChange={(event) => updateField('project', 'name', event.target.value)}
            />
          </label>
          <label>
            Department
            <input
              value={projectData.project.department}
              onChange={(event) => updateField('project', 'department', event.target.value)}
            />
          </label>
          <label>
            Business Unit
            <input value="Retail Ops" readOnly />
          </label>
          <label>
            Project Sponsor
            <input
              value={projectData.project.sponsor}
              onChange={(event) => updateField('project', 'sponsor', event.target.value)}
            />
          </label>
          <label>
            Expected Completion
            <input value="2026-08-15" readOnly />
          </label>
        </div>
        <div className="hero-actions">
          <button className="primary" onClick={() => setActivePage('interview')}>
            Start Interview
          </button>
        </div>
      </section>
    </div>
  )

  const renderInterview = () => (
    <div className="interview-shell">
      <div className="panel-header interview-header">
        <div>
          <p className="eyebrow">AI Interview</p>
          <h2>Interview Workspace</h2>
        </div>
        <button className="secondary" onClick={() => setActivePage('review')}>
          Go to Review
        </button>
      </div>

      <div className="workspace-grid">
        <section className="panel">
          <h3>Progress</h3>
          <ul className="progress-list">
            {progressItems.map((step) => (
              <li key={step.label} className={step.complete ? 'done' : ''}>
                <span>{step.complete ? '✓' : '○'}</span>
                {step.label}
              </li>
            ))}
          </ul>
        </section>

        <section className="panel chat-panel">
          <h3>Chat</h3>
          <div className="message-list">
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <strong>{message.role === 'ai' ? 'AI' : 'Customer'}</strong>
                <p>{message.text}</p>
              </div>
            ))}
          </div>

          <div className="suggestions">
            <span>Suggested questions</span>
            {['Existing software?', 'Number of users?', 'Reports?', 'Integrations?'].map((item) => (
              <button key={item} className="chip" onClick={() => setDraftInput(item)}>
                {item}
              </button>
            ))}
          </div>

          <form className="composer" onSubmit={handleSend}>
            <input
              value={draftInput}
              onChange={(event) => setDraftInput(event.target.value)}
              placeholder="Type your answer..."
            />
            <button className="primary" type="submit">
              Send
            </button>
          </form>
        </section>

        <section className="panel">
          <h3>Live FDF</h3>
          <label>
            Project Overview
            <textarea
              value={projectData.overview.description}
              onChange={(event) => updateField('overview', 'description', event.target.value)}
            />
          </label>
          <label>
            Stakeholders
            <input value={projectData.overview.stakeholders.join(', ')} readOnly />
          </label>
          <label>
            Business Goals
            <textarea
              value={projectData.discovery.business_goals}
              onChange={(event) => updateField('discovery', 'business_goals', event.target.value)}
            />
          </label>
        </section>

        <section className="panel">
          <h3>Missing Fields</h3>
          <ul className="missing-list">
            {projectData.missing_fields.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h3>Timeline</h3>
          <div className="timeline">
            <div>
              <strong>10:02</strong>
              <p>Overview completed</p>
            </div>
            <div>
              <strong>10:08</strong>
              <p>Business problem extracted</p>
            </div>
            <div>
              <strong>10:14</strong>
              <p>Stakeholders added</p>
            </div>
          </div>
        </section>

        <section className="panel">
          <h3>Requirement Cards</h3>
          {projectData.functional_requirements.map((item) => (
            <div key={item.title} className="requirement-card">
              <strong>{item.title}</strong>
              <p>Priority: {item.priority}</p>
              <p>Confidence: {(item.confidence * 100).toFixed(0)}%</p>
              <p>Source: Conversation 18</p>
            </div>
          ))}
        </section>
      </div>

      {notice && (
        <div className="toast">
          <strong>{notice.title}</strong>
          <p>{notice.detail}</p>
        </div>
      )}
    </div>
  )

  const renderReview = () => (
    <div className="page-grid review-grid">
      <section className="page review-card">
        <div className="section-heading">
          <h2>Requirement Discovery Complete</h2>
          <span className="badge success">{completion}%</span>
        </div>
        <div className="review-actions">
          <button className="secondary">Edit Overview</button>
          <button className="secondary">Edit Discovery</button>
          <button className="secondary">Edit Functional Requirements</button>
          <button className="secondary">Edit Security</button>
          <button className="primary">Generate DOCX</button>
          <button className="secondary">Generate PDF</button>
          <button className="secondary">Export JSON</button>
        </div>
        <div className="preview-card">
          <div className="preview-heading">
            <h3>Document Preview</h3>
            <span className="badge">HTML preview</span>
          </div>
          <div className="preview-pages">
            <div className="preview-page">
              <h4>Requirement Discovery Form</h4>
              <p>{projectData.project.name}</p>
              <p>{projectData.overview.description}</p>
            </div>
            <div className="preview-page">
              <h4>Page 2</h4>
              <p>{projectData.discovery.business_problem}</p>
              <p>{projectData.discovery.business_goals}</p>
            </div>
            <div className="preview-page">
              <h4>Page 3</h4>
              <p>Requirements: {projectData.functional_requirements.map((item) => item.title).join(', ')}</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  )

  const renderExport = () => (
    <div className="page centered-page">
      <section className="page export-card">
        <h2>Export Ready</h2>
        <p className="muted">The frontend consumes structured backend data and presents it as a polished document.</p>
        <pre>{JSON.stringify(projectData, null, 2)}</pre>
      </section>
    </div>
  )

  return (
    <div className="app-shell">
      <header className="header">
        <div>
          <p className="eyebrow">BA Agent</p>
          <h2>Business Analyst AI</h2>
        </div>
        <div className="profile-pill">Profile</div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activePage === item.id ? 'active' : ''}`}
              onClick={() => setActivePage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </aside>

        <main className="main-content">
          {activePage === 'dashboard' && renderDashboard()}
          {activePage === 'new-project' && renderNewProject()}
          {activePage === 'interview' && renderInterview()}
          {activePage === 'review' && renderReview()}
          {activePage === 'export' && renderExport()}
        </main>
      </div>
    </div>
  )
}

export default App
