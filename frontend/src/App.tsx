import { useEffect, useState, type FormEvent, type ChangeEvent } from 'react'
import './App.css'

type PageView = 'dashboard' | 'new-project' | 'interview' | 'review' | 'export'
type MessageRole = 'ai' | 'user'
type UpdateSection = 'project' | 'overview' | 'discovery'

interface Requirement {
  title: string
  priority: string
  confidence: number
}

interface ProjectData {
  project: {
    name: string
    department: string
    sponsor: string
    business_unit: string
    expected_completion: string
  }
  overview: {
    description: string
    stakeholders: string[]
  }
  discovery: {
    business_problem: string
    business_goals: string
    desired_outcomes: string
    constraints: string
  }
  functional_requirements: Requirement[]
  missing_fields: string[]
  next_question: string
}

interface Message {
  role: MessageRole
  text: string
}

interface Notice {
  title: string
  detail: string
}

const initialProject: ProjectData = {
  project: {
    name: '',
    department: '',
    sponsor: '',
    business_unit: '',
    expected_completion: '',
  },
  overview: {
    description: '',
    stakeholders: [],
  },
  discovery: {
    business_problem: '',
    business_goals: '',
    desired_outcomes: '',
    constraints: '',
  },
  functional_requirements: [],
  missing_fields: [],
  next_question: '',
}

const initialMessages: Message[] = [
  { role: 'ai', text: 'Hello. Tell me about your project and the business problem you want to solve.' },
]

const navItems: Array<{ id: PageView; label: string }> = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'new-project', label: 'New Project' },
  { id: 'interview', label: 'Interview Workspace' },
  { id: 'review', label: 'Review' },
  { id: 'export', label: 'Export' },
]

function App() {
  const [activePage, setActivePage] = useState<PageView>('dashboard')
  const [projectData, setProjectData] = useState<ProjectData>(initialProject)
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [draftInput, setDraftInput] = useState<string>('')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)

  useEffect(() => {
    const syncProjectData = async () => {
      try {
        await fetch('http://127.0.0.1:8000/api/project', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(projectData),
        })
      } catch (error) {
        console.error('Failed to sync project data', error)
      }
    }

    void syncProjectData()
  }, [projectData])

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

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const incoming = draftInput.trim()
    if (!incoming) return

    setMessages((prev) => [...prev, { role: 'user', text: incoming }])
    setDraftInput('')
    setIsLoading(true)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: incoming }),
      })

      const payload = (await response.json()) as {
        status?: string
        data?: Record<string, unknown>
        detail?: unknown
      }

      const lower = incoming.toLowerCase()
      const replyText = typeof payload?.data?.text === 'string'
        ? payload.data.text
        : typeof payload?.data?.reply === 'string'
          ? payload.data.reply
          : typeof payload?.data?.message === 'string'
            ? payload.data.message
            : typeof payload?.data?.output === 'object' && payload.data.output !== null && 'content' in payload.data.output
              ? String((payload.data.output as { content?: unknown }).content ?? '')
              : typeof payload?.detail === 'string'
                ? payload.detail
                : 'I have captured that input and I will keep advancing the discovery flow.'

      setMessages((prev) => [...prev, { role: 'ai', text: replyText }])

      if (lower.includes('kpi') || lower.includes('requirement')) {
        setNotice({ title: 'Requirement Added', detail: 'Business goal captured with confidence' })
        setTimeout(() => setNotice(null), 1800)
      }
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'ai', text: 'The assistant is unavailable right now. Please try again in a moment.' }])
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const updateField = (section: UpdateSection, key: string, value: string) => {
    setProjectData((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] as Record<string, string>),
        [key]: value,
      },
    }))
  }

  const handleReviewAction = (action: string) => {
    if (action.startsWith('Edit')) {
      setActivePage('interview')
      setNotice({ title: action, detail: 'Opened the interview workspace for editing.' })
      setTimeout(() => setNotice(null), 1800)
      return
    }

    setNotice({ title: action, detail: 'Prepared for export and review.' })
    setTimeout(() => setNotice(null), 1800)
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
              placeholder="Enter project name"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'name', event.target.value)}
            />
          </label>
          <label>
            Department
            <input
              value={projectData.project.department}
              placeholder="Enter department"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'department', event.target.value)}
            />
          </label>
          <label>
            Business Unit
            <input
              value={projectData.project.business_unit}
              placeholder="Enter business unit"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'business_unit', event.target.value)}
            />
          </label>
          <label>
            Project Sponsor
            <input
              value={projectData.project.sponsor}
              placeholder="Enter sponsor name"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'sponsor', event.target.value)}
            />
          </label>
          <label>
            Expected Completion
            <input
              value={projectData.project.expected_completion}
              placeholder="YYYY-MM-DD"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'expected_completion', event.target.value)}
            />
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
              onChange={(event: ChangeEvent<HTMLInputElement>) => setDraftInput(event.target.value)}
              placeholder="Type your answer..."
            />
            <button className="primary" type="submit" disabled={isLoading}>
              {isLoading ? 'Sending…' : 'Send'}
            </button>
          </form>
        </section>

        <section className="panel">
          <h3>Live FDF</h3>
          <label>
            Project Overview
            <textarea
              value={projectData.overview.description}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField('overview', 'description', event.target.value)}
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
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField('discovery', 'business_goals', event.target.value)}
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
          <button className="secondary" onClick={() => handleReviewAction('Edit Overview')}>
            Edit Overview
          </button>
          <button className="secondary" onClick={() => handleReviewAction('Edit Discovery')}>
            Edit Discovery
          </button>
          <button className="secondary" onClick={() => handleReviewAction('Edit Functional Requirements')}>
            Edit Functional Requirements
          </button>
          <button className="secondary" onClick={() => handleReviewAction('Edit Security')}>
            Edit Security
          </button>
          <button className="primary" onClick={() => handleReviewAction('Generate DOCX')}>
            Generate DOCX
          </button>
          <button className="secondary" onClick={() => handleReviewAction('Generate PDF')}>
            Generate PDF
          </button>
          <button className="secondary" onClick={() => handleReviewAction('Export JSON')}>
            Export JSON
          </button>
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
