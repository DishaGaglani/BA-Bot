import { useEffect, useState, useRef, type FormEvent, type ChangeEvent } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
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

const navItems: Array<{ id: PageView; label: string; code: string }> = [
  { id: 'dashboard', label: 'Dashboard', code: 'DB' },
  { id: 'new-project', label: 'New Project', code: 'NP' },
  { id: 'interview', label: 'Interview Workspace', code: 'IW' },
  { id: 'review', label: 'Review', code: 'RV' },
  { id: 'export', label: 'Export', code: 'EX' },
]

function parseInlineMarkdown(text: string): React.ReactNode {
  const inlineRegex = /(\*\*.*?\*\*|`.*?`)/g;
  const parts = text.split(inlineRegex);
  
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={index}
          style={{
            backgroundColor: '#f0f2f5',
            padding: '2px 4px',
            borderRadius: '4px',
            fontFamily: 'monospace',
          }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function parseMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n');
  return lines.map((line, lineIndex) => {
    if (line.startsWith('### ')) {
      return <h4 key={lineIndex}>{parseInlineMarkdown(line.slice(4))}</h4>;
    }
    if (line.startsWith('## ')) {
      return <h3 key={lineIndex}>{parseInlineMarkdown(line.slice(3))}</h3>;
    }
    if (line.startsWith('# ')) {
      return <h2 key={lineIndex}>{parseInlineMarkdown(line.slice(2))}</h2>;
    }

    const bulletMatch = line.match(/^(\s*)[-*+]\s+(.*)/);
    if (bulletMatch) {
      return (
        <div key={lineIndex} style={{ margin: '4px 0 4px 20px', display: 'flex', gap: '8px' }}>
          <span style={{ userSelect: 'none' }}>•</span>
          <span>{parseInlineMarkdown(bulletMatch[2])}</span>
        </div>
      );
    }
    
    const numMatch = line.match(/^(\s*)(\d+)\.\s+(.*)/);
    if (numMatch) {
      return (
        <div key={lineIndex} style={{ margin: '4px 0 4px 20px', display: 'flex', gap: '8px' }}>
          <span style={{ userSelect: 'none' }}>{numMatch[2]}.</span>
          <span>{parseInlineMarkdown(numMatch[3])}</span>
        </div>
      );
    }

    if (line.trim() === '') {
      return <div key={lineIndex} style={{ height: '0.8em' }} />;
    }

    return (
      <span key={lineIndex} style={{ display: 'block', margin: '4px 0' }}>
        {parseInlineMarkdown(line)}
      </span>
    );
  });
}

function parseContent(text: string): React.ReactNode {
  const mathRegex = /(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$[^\$\n]+?\$|\\\([\s\S]*?\\\))/g;
  const parts = text.split(mathRegex);
  
  return parts.map((part, index) => {
    if (part.startsWith('$$') && part.endsWith('$$')) {
      const math = part.slice(2, -2).trim();
      try {
        const html = katex.renderToString(math, { displayMode: true, throwOnError: false });
        return <div key={index} dangerouslySetInnerHTML={{ __html: html }} className="katex-block" />;
      } catch (e) {
        return <code key={index}>{part}</code>;
      }
    }
    if (part.startsWith('\\\[') && part.endsWith('\\\]')) {
      const math = part.slice(2, -2).trim();
      try {
        const html = katex.renderToString(math, { displayMode: true, throwOnError: false });
        return <div key={index} dangerouslySetInnerHTML={{ __html: html }} className="katex-block" />;
      } catch (e) {
        return <code key={index}>{part}</code>;
      }
    }
    if (part.startsWith('$') && part.endsWith('$')) {
      const math = part.slice(1, -1).trim();
      try {
        const html = katex.renderToString(math, { displayMode: false, throwOnError: false });
        return <span key={index} dangerouslySetInnerHTML={{ __html: html }} className="katex-inline" />;
      } catch (e) {
        return <code key={index}>{part}</code>;
      }
    }
    if (part.startsWith('\\(') && part.endsWith('\\)')) {
      const math = part.slice(2, -2).trim();
      try {
        const html = katex.renderToString(math, { displayMode: false, throwOnError: false });
        return <span key={index} dangerouslySetInnerHTML={{ __html: html }} className="katex-inline" />;
      } catch (e) {
        return <code key={index}>{part}</code>;
      }
    }
    
    return <span key={index}>{parseMarkdown(part)}</span>;
  });
}

function App() {
  const [activePage, setActivePage] = useState<PageView>('dashboard')
  const [projectData, setProjectData] = useState<ProjectData>(initialProject)
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [draftInput, setDraftInput] = useState<string>('')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false)
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem('ba_bot_session_id'))
  const [isLoaded, setIsLoaded] = useState<boolean>(false)

  const messageListRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    const loadProjectData = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8000/api/project')
        if (response.ok) {
          const data = await response.json()
          if (data) {
            setProjectData(data)
          }
        }
      } catch (error) {
        console.error('Failed to load project data', error)
      } finally {
        setIsLoaded(true)
      }
    }
    void loadProjectData()
  }, [])

  useEffect(() => {
    if (!isLoaded) return

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
  }, [projectData, isLoaded])

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

    setMessages((prev) => [
      ...prev,
      { role: 'user', text: incoming },
      { role: 'ai', text: '' },
    ])
    setDraftInput('')
    setIsLoading(true)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: incoming, sessionId: sessionId }),
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No readable response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let fullReply = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const lines = part.split('\n')
          for (const line of lines) {
            if (line.startsWith('data:')) {
              const dataStr = line.slice(5).trim()
              try {
                const parsed = JSON.parse(dataStr) as {
                  event?: string
                  data?: unknown
                  message?: string
                  details?: string
                }

                if (parsed.event === 'token' && typeof parsed.data === 'string') {
                  fullReply += parsed.data
                  setMessages((prev) => {
                    const updated = [...prev]
                    if (updated.length > 0) {
                      const last = updated[updated.length - 1]
                      if (last.role === 'ai') {
                        last.text = fullReply
                      }
                    }
                    return updated
                  })
                } else if (parsed.event === 'nextAgentFlow' && (parsed.data as { status?: string })?.status === 'INPROGRESS') {
                  fullReply = ''
                } else if (parsed.event === 'metadata' && parsed.data) {
                  const meta = parsed.data as { sessionId?: string }
                  if (meta.sessionId) {
                    setSessionId(meta.sessionId)
                    localStorage.setItem('ba_bot_session_id', meta.sessionId)
                  }
                } else if (parsed.event === 'error') {
                  const errMsg = parsed.message || 'Stream error occurred'
                  console.error(errMsg, parsed.details)
                  setMessages((prev) => {
                    const updated = [...prev]
                    if (updated.length > 0) {
                      const last = updated[updated.length - 1]
                      if (last.role === 'ai') {
                        last.text = last.text ? `${last.text}\n[Error: ${errMsg}]` : `Error: ${errMsg}`
                      }
                    }
                    return updated
                  })
                }
              } catch (e) {
                console.error('Failed to parse SSE payload:', dataStr, e)
              }
            }
          }
        }
      }

      const lower = incoming.toLowerCase()
      if (lower.includes('kpi') || lower.includes('requirement')) {
        setNotice({ title: 'Requirement Added', detail: 'Business goal captured with confidence' })
        setTimeout(() => setNotice(null), 1800)
      }
    } catch (error) {
      setMessages((prev) => {
        const updated = [...prev]
        if (updated.length > 0 && updated[updated.length - 1].role === 'ai' && !updated[updated.length - 1].text) {
          updated[updated.length - 1].text = 'The assistant is unavailable right now. Please try again in a moment.'
          return updated
        }
        return [...prev, { role: 'ai', text: 'The assistant is unavailable right now. Please try again in a moment.' }]
      })
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

  const handleStartNewInterview = () => {
    setSessionId(null)
    localStorage.removeItem('ba_bot_session_id')
    setMessages(initialMessages)
    setActivePage('interview')
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
          <button className="primary" onClick={handleStartNewInterview}>
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

      <div className="workspace-grid" style={{ gridTemplateColumns: '1fr' }}>
        <section className="panel chat-panel" style={{ gridColumn: 'span 1' }}>
          <h3>Chat</h3>
          <div className="message-list" ref={messageListRef} style={{ minHeight: '450px', maxHeight: '60vh', overflowY: 'auto' }}>
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <strong>{message.role === 'ai' ? 'AI' : 'Customer'}</strong>
                <div>{parseContent(message.text)}</div>
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
    <div className="review-workspace-layout">
      <div className="review-main-column">
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
          </div>
          <div className="preview-card">
            <div className="preview-heading">
              <h3>Document Preview</h3>
              <span className="badge">HTML preview</span>
            </div>
            <div className="preview-pages">
              <div className="preview-page">
                <h4>Requirement Discovery Form</h4>
                <p>{projectData.project.name || <em style={{ color: '#aaa' }}>No project name</em>}</p>
                <p>{projectData.overview.description || <em style={{ color: '#aaa' }}>No description</em>}</p>
              </div>
              <div className="preview-page">
                <h4>Page 2</h4>
                <p>{projectData.discovery.business_problem || <em style={{ color: '#aaa' }}>No business problem</em>}</p>
                <p>{projectData.discovery.business_goals || <em style={{ color: '#aaa' }}>No business goals</em>}</p>
              </div>
              <div className="preview-page">
                <h4>Page 3</h4>
                <p>
                  Requirements:{' '}
                  {projectData.functional_requirements.length > 0 ? (
                    projectData.functional_requirements.map((item) => item.title).join(', ')
                  ) : (
                    <em style={{ color: '#aaa' }}>No requirements captured</em>
                  )}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="review-status-column">
        <section className="panel">
          <h3>Requirement Cards</h3>
          {projectData.functional_requirements.length > 0 ? (
            projectData.functional_requirements.map((item) => (
              <div key={item.title} className="requirement-card">
                <strong>{item.title}</strong>
                <p>Priority: {item.priority}</p>
                <p>Confidence: {(item.confidence * 100).toFixed(0)}%</p>
                <p>Source: Conversation 18</p>
              </div>
            ))
          ) : (
            <p className="muted" style={{ fontStyle: 'italic', fontSize: '0.9rem' }}>No requirements extracted yet.</p>
          )}
        </section>

        <section className="panel">
          <h3>Missing Fields</h3>
          {projectData.missing_fields.length > 0 ? (
            <ul className="missing-list">
              {projectData.missing_fields.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted" style={{ fontStyle: 'italic', fontSize: '0.9rem', color: '#0f7b45' }}>✓ All fields complete!</p>
          )}
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
      </div>
    </div>
  )

  const renderExport = () => (
    <div className="page centered-page">
      <section className="page export-card">
        <h2>Export Project Requirements</h2>
        <p className="muted" style={{ marginBottom: '24px' }}>
          Select your preferred document format to download and share the compiled discovery results.
        </p>
        
        <div className="export-options-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
          <div className="export-option-card" style={{ border: '1px solid #e7ebf2', padding: '24px', borderRadius: '16px', backgroundColor: '#fcfdff', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', height: '36px' }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#3755d4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            </span>
            <h3 style={{ margin: '0' }}>Microsoft Word Document</h3>
            <p className="muted" style={{ fontSize: '0.9rem', margin: '0', flex: 1 }}>
              Download the fully structured discovery report as an editable Word Document (.docx) formatted with standard headings and layout.
            </p>
            <button className="primary" onClick={() => handleReviewAction('Generate DOCX')} style={{ width: '100%', marginTop: '12px' }}>
              Export as Word (.docx)
            </button>
          </div>

          <div className="export-option-card" style={{ border: '1px solid #e7ebf2', padding: '24px', borderRadius: '16px', backgroundColor: '#fcfdff', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', height: '36px' }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#e11d48" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M9 15h1a1.5 1.5 0 0 0 0-3H9v4z"></path><path d="M12 12v4"></path><path d="M12 12a2 2 0 0 1 2 2v0a2 2 0 0 1-2 2"></path></svg>
            </span>
            <h3 style={{ margin: '0' }}>Adobe PDF Document</h3>
            <p className="muted" style={{ fontSize: '0.9rem', margin: '0', flex: 1 }}>
              Generate a print-ready, read-only PDF document (.pdf) containing all extracted functional requirements, timeline details, and business outcomes.
            </p>
            <button className="primary" onClick={() => handleReviewAction('Generate PDF')} style={{ width: '100%', marginTop: '12px' }}>
              Export as PDF (.pdf)
            </button>
          </div>
        </div>
      </section>
    </div>
  )

  return (
    <div className="app-shell">
      {activePage !== 'interview' && (
        <header className="header">
          <div>
            <p className="eyebrow">BA Agent</p>
            <h2>Business Analyst AI</h2>
          </div>
          <div className="profile-pill">Profile</div>
        </header>
      )}

      <div className="workspace">
        <aside className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`}>
          <button
            className="sidebar-toggle"
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            title={isSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
          >
            <span>{isSidebarCollapsed ? '▶' : '◀'}</span>
            {!isSidebarCollapsed && <span>Collapse</span>}
          </button>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activePage === item.id ? 'active' : ''}`}
              onClick={() => setActivePage(item.id)}
              title={item.label}
              style={{ display: 'flex', alignItems: 'center', gap: isSidebarCollapsed ? '0' : '12px' }}
            >
              {isSidebarCollapsed ? (
                <span className="collapsed-initials">{item.code}</span>
              ) : (
                <span>{item.label}</span>
              )}
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
