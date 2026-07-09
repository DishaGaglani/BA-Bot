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
  id?: number
  sessionId?: string | null
  messages?: Message[]
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

const initialMessages: Message[] = [
  { role: 'ai', text: 'Hello. Tell me about your project and the business problem you want to solve.' },
]

const initialProject: ProjectData = {
  id: undefined,
  sessionId: null,
  messages: initialMessages,
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

const navItems: Array<{ id: PageView; label: string; code: string }> = [
  { id: 'dashboard', label: 'Dashboard', code: 'DB' },
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
  const [draftInput, setDraftInput] = useState<string>('')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false)
  const [isLoaded, setIsLoaded] = useState<boolean>(false)

  const [projectsList, setProjectsList] = useState<ProjectData[]>([])
  const [activeProjectId, setActiveProjectId] = useState<number | null>(() => {
    const saved = localStorage.getItem('ba_bot_active_project_id')
    return saved ? parseInt(saved, 10) : null
  })

  const messageListRef = useRef<HTMLDivElement | null>(null)

  const chatMessages = projectData.messages || initialMessages
  const currentSessionId = projectData.sessionId || null

  const calculateCompletion = (proj: ProjectData) => {
    const hasProjectName = proj.project?.name;
    const hasOverviewDesc = proj.overview?.description;
    const hasDiscoveryProblem = proj.discovery?.business_problem;
    const hasDiscoveryGoals = proj.discovery?.business_goals;
    const hasFunctionalReqs = proj.functional_requirements && proj.functional_requirements.length > 0;
    
    return Math.round(
      (Number(Boolean(hasProjectName)) +
        Number(Boolean(hasOverviewDesc)) +
        Number(Boolean(hasDiscoveryProblem)) +
        Number(Boolean(hasDiscoveryGoals)) +
        Number(Boolean(hasFunctionalReqs))) /
        5 *
        100,
    )
  }

  const loadProjects = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/projects')
      if (response.ok) {
        const list = await response.json()
        setProjectsList(list)
        return list
      }
    } catch (error) {
      console.error('Failed to load projects list', error)
    }
    return []
  }

  const handleLoadProject = async (id: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/project/${id}`)
      if (response.ok) {
        const proj = await response.json()
        setActiveProjectId(id)
        localStorage.setItem('ba_bot_active_project_id', id.toString())
        setProjectData(proj)
        setActivePage('interview')
      }
    } catch (error) {
      console.error('Failed to load project details', error)
    }
  }

  const handleDeleteProject = async (id: number) => {
    if (!confirm('Are you sure you want to delete this project?')) return
    
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/project/${id}`, {
        method: 'DELETE',
      })
      if (response.ok) {
        if (activeProjectId === id) {
          setActiveProjectId(null)
          localStorage.removeItem('ba_bot_active_project_id')
          setProjectData(initialProject)
        }
        await loadProjects()
        setNotice({ title: 'Project Deleted', detail: 'The project was successfully removed.' })
        setTimeout(() => setNotice(null), 1800)
      }
    } catch (error) {
      console.error('Failed to delete project', error)
    }
  }

  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight
    }
  }, [chatMessages])

  useEffect(() => {
    const initData = async () => {
      const list = await loadProjects()
      setIsLoaded(true)
      
      if (activeProjectId) {
        const found = list.find((p: ProjectData) => p.id === activeProjectId)
        if (found) {
          setProjectData(found)
        } else {
          setActiveProjectId(null)
          localStorage.removeItem('ba_bot_active_project_id')
        }
      }
    }
    void initData()
  }, [])

  useEffect(() => {
    if (!isLoaded || !activeProjectId || projectData.id !== activeProjectId) return

    const syncProjectData = async () => {
      try {
        await fetch(`http://127.0.0.1:8000/api/project/${activeProjectId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(projectData),
        })
        
        setProjectsList((prev) =>
          prev.map((p) => (p.id === activeProjectId ? { ...projectData, id: activeProjectId } : p))
        )
      } catch (error) {
        console.error('Failed to sync project data', error)
      }
    }

    const timer = setTimeout(() => {
      void syncProjectData()
    }, 500)

    return () => clearTimeout(timer)
  }, [projectData, activeProjectId, isLoaded])

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

    setProjectData((prev) => ({
      ...prev,
      messages: [
        ...(prev.messages || initialMessages),
        { role: 'user', text: incoming },
        { role: 'ai', text: '' },
      ],
    }))
    setDraftInput('')
    setIsLoading(true)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: incoming, sessionId: currentSessionId, projectId: activeProjectId }),
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
                  setProjectData((prev) => {
                    const updatedMessages = [...(prev.messages || initialMessages)]
                    if (updatedMessages.length > 0) {
                      const last = updatedMessages[updatedMessages.length - 1]
                      if (last.role === 'ai') {
                        last.text = fullReply
                      }
                    }
                    return {
                      ...prev,
                      messages: updatedMessages,
                    }
                  })
                } else if (parsed.event === 'nextAgentFlow' && (parsed.data as { status?: string })?.status === 'INPROGRESS') {
                  fullReply = ''
                } else if (parsed.event === 'metadata' && parsed.data) {
                  const meta = parsed.data as { sessionId?: string }
                  if (meta.sessionId) {
                    setProjectData((prev) => ({
                      ...prev,
                      sessionId: meta.sessionId,
                    }))
                  }
                } else if (parsed.event === 'error') {
                  const errMsg = parsed.message || 'Stream error occurred'
                  console.error(errMsg, parsed.details)
                  setProjectData((prev) => {
                    const updatedMessages = [...(prev.messages || initialMessages)]
                    if (updatedMessages.length > 0) {
                      const last = updatedMessages[updatedMessages.length - 1]
                      if (last.role === 'ai') {
                        last.text = last.text ? `${last.text}\n[Error: ${errMsg}]` : `Error: ${errMsg}`
                      }
                    }
                    return {
                      ...prev,
                      messages: updatedMessages,
                    }
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
      setProjectData((prev) => {
        const updatedMessages = [...(prev.messages || initialMessages)]
        if (updatedMessages.length > 0 && updatedMessages[updatedMessages.length - 1].role === 'ai' && !updatedMessages[updatedMessages.length - 1].text) {
          updatedMessages[updatedMessages.length - 1].text = 'The assistant is unavailable right now. Please try again in a moment.'
          return { ...prev, messages: updatedMessages }
        }
        return {
          ...prev,
          messages: [...updatedMessages, { role: 'ai', text: 'The assistant is unavailable right now. Please try again in a moment.' }],
        }
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

  const handleStartNewInterview = async () => {
    const newProjPayload: ProjectData = {
      ...projectData,
      messages: initialMessages,
      sessionId: null,
    }

    try {
      setIsLoading(true)
      const response = await fetch('http://127.0.0.1:8000/api/project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProjPayload),
      })
      
      if (response.ok) {
        const createdProj = await response.json()
        const newId = createdProj.id
        
        setActiveProjectId(newId)
        localStorage.setItem('ba_bot_active_project_id', newId.toString())
        setProjectData(createdProj)
        
        await loadProjects()
        setActivePage('interview')
      }
    } catch (error) {
      console.error('Failed to create new project', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleClearConversation = async () => {
    if (!activeProjectId) return;
    if (!confirm('Are you sure you want to clear the conversation history?')) return;
    
    const updatedProject = {
      ...projectData,
      messages: initialMessages,
      sessionId: null,
    };
    setProjectData(updatedProject);

    try {
      await fetch(`http://127.0.0.1:8000/api/project/${activeProjectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedProject),
      });
      setNotice({ title: 'Chat Cleared', detail: 'Conversation history reset successfully.' });
      setTimeout(() => setNotice(null), 1800);
    } catch (error) {
      console.error('Failed to clear chat on backend', error);
    }
  };

  const handleReviewAction = async (action: string) => {
    if (action.startsWith('Edit')) {
      setActivePage('interview')
      setNotice({ title: action, detail: 'Opened the interview workspace for editing.' })
      setTimeout(() => setNotice(null), 1800)
      return
    }

    if (!activeProjectId) {
      setNotice({ title: 'Export Failed', detail: 'No active project selected.' })
      setTimeout(() => setNotice(null), 1800)
      return
    }

    let format = ''
    if (action.includes('DOCX') || action.includes('Word')) {
      format = 'docx'
    } else if (action.includes('PDF')) {
      format = 'pdf'
    }

    if (format) {
      setNotice({ title: 'Generating Document', detail: 'Compiling conversation history with AI, please wait...' })
      setIsLoading(true)
      
      try {
        const response = await fetch(`http://127.0.0.1:8000/api/project/${activeProjectId}/export?format=${format}`)
        if (!response.ok) {
          throw new Error('Export request failed')
        }
        
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const projectSlug = (projectData.project?.name || 'project').replace(/\s+/g, '_')
        a.download = `${projectSlug}_requirements.${format}`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        window.URL.revokeObjectURL(url)
        
        setNotice({ title: 'Export Success', detail: `Downloaded FDR ${format.toUpperCase()} successfully.` })
      } catch (error) {
        console.error('Failed to export document', error)
        setNotice({ title: 'Export Error', detail: 'Failed to compile discovery document.' })
      } finally {
        setIsLoading(false)
        setTimeout(() => setNotice(null), 1800)
      }
      return
    }

    setNotice({ title: action, detail: 'Prepared for export and review.' })
    setTimeout(() => setNotice(null), 1800)
  }

  const renderDashboard = () => {
    const totalProjects = projectsList.length
    const completedProjects = projectsList.filter(p => calculateCompletion(p) === 100).length
    const pendingProjects = totalProjects - completedProjects
    const hoursSaved = completedProjects * 6

    return (
      <div className="dashboard-layout" style={{ display: 'flex', flexDirection: 'column', gap: '32px', width: '100%' }}>
        <section className="page">
          <div className="section-heading">
            <h2>Projects</h2>
            <span className="badge">{totalProjects} active</span>
          </div>
          <div 
            className="projects-grid" 
            style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', 
              gap: '24px', 
              marginTop: '20px' 
            }}
          >
            <article 
              className="project-tile plus-tile" 
              onClick={() => {
                setProjectData(initialProject)
                setActivePage('new-project')
              }}
              style={{
                border: '2px dashed #b2c5df',
                borderRadius: '16px',
                padding: '24px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '180px',
                cursor: 'pointer',
                backgroundColor: '#fcfdff',
                transition: 'all 0.2s ease',
              }}
            >
              <span style={{ fontSize: '3.5rem', color: '#3755d4', lineHeight: 1 }}>+</span>
              <span style={{ fontWeight: '600', color: '#4b5c77', marginTop: '12px' }}>New Project</span>
            </article>

            {projectsList.map((p) => {
              const comp = calculateCompletion(p);
              return (
                <article 
                  key={p.id} 
                  className="project-tile"
                  style={{
                    border: '1px solid #e7ebf2',
                    borderRadius: '16px',
                    padding: '24px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    minHeight: '180px',
                    backgroundColor: '#ffffff',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
                    position: 'relative',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleLoadProject(p.id!)}
                >
                  <div style={{ paddingRight: '24px' }}>
                    <h3 style={{ margin: '0 0 8px 0', fontSize: '1.2rem', color: '#1e293b' }}>
                      {p.project?.name || 'Untitled Project'}
                    </h3>
                    <p style={{ margin: '0', fontSize: '0.85rem', color: '#64748b' }}>Dept: {p.project?.department || 'N/A'}</p>
                    <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>Sponsor: {p.project?.sponsor || 'N/A'}</p>
                  </div>
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#475569', marginBottom: '4px' }}>
                      <span>Progress</span>
                      <strong>{comp}%</strong>
                    </div>
                    <div style={{ height: '6px', width: '100%', backgroundColor: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${comp}%`, backgroundColor: comp === 100 ? '#10b981' : '#3755d4', borderRadius: '3px' }} />
                    </div>
                  </div>
                  <button 
                    style={{
                      position: 'absolute',
                      top: '16px',
                      right: '16px',
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      fontSize: '1.2rem',
                      padding: '4px',
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(p.id!);
                    }}
                    title="Delete Project"
                  >
                    🗑️
                  </button>
                </article>
              );
            })}
          </div>
        </section>

        <section className="page">
          <div className="section-heading">
            <h2>Analytics</h2>
          </div>
          <div className="stats-grid">
            <article className="stat-card">
              <span className="stat-label">Total Projects</span>
              <strong>{totalProjects}</strong>
            </article>
            <article className="stat-card">
              <span className="stat-label">Completed</span>
              <strong>{completedProjects}</strong>
            </article>
            <article className="stat-card">
              <span className="stat-label">Pending</span>
              <strong>{pendingProjects}</strong>
            </article>
            <article className="stat-card">
              <span className="stat-label">Hours Saved</span>
              <strong>{hoursSaved}</strong>
            </article>
          </div>
        </section>
      </div>
    )
  }

  const renderNewProject = () => (
    <div className="page centered-page" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '16px' }}>
      <button 
        className="secondary" 
        onClick={() => setActivePage('dashboard')}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', fontSize: '0.9rem' }}
      >
        ⬅ Back to Dashboard
      </button>
      <section className="page form-card" style={{ width: '100%' }}>
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
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <button 
            className="secondary" 
            onClick={() => setActivePage('dashboard')}
            style={{ padding: '8px 14px', fontSize: '0.9rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            ⬅ Back to Dashboard
          </button>
          <div>
            <p className="eyebrow">AI Interview</p>
            <h2>Interview Workspace</h2>
          </div>
        </div>
        <button className="secondary" onClick={() => setActivePage('review')}>
          Go to Review
        </button>
      </div>

      <div className="workspace-grid" style={{ gridTemplateColumns: '1fr' }}>
        <section className="panel chat-panel" style={{ gridColumn: 'span 1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: '0' }}>Chat</h3>
            <button 
              className="secondary" 
              onClick={handleClearConversation}
              style={{ fontSize: '0.85rem', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
            >
              🗑️ Clear Chat
            </button>
          </div>
          <div className="message-list" ref={messageListRef} style={{ minHeight: '450px', maxHeight: '60vh', overflowY: 'auto' }}>
            {chatMessages.map((message, index) => (
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
      <div style={{ gridColumn: 'span 2', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid #e7ebf2' }}>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <button 
            className="secondary" 
            onClick={() => setActivePage('dashboard')}
            style={{ padding: '8px 14px', fontSize: '0.9rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            ⬅ Back to Dashboard
          </button>
          <div>
            <p className="eyebrow">Review Workspace</p>
            <h2>Compile &amp; Export Requirements</h2>
          </div>
        </div>
        <button className="primary" onClick={() => setActivePage('interview')}>
          Back to Chat
        </button>
      </div>

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
                <p>{projectData.project?.name || <em style={{ color: '#aaa' }}>No project name</em>}</p>
                <p>{projectData.overview?.description || <em style={{ color: '#aaa' }}>No description</em>}</p>
              </div>
              <div className="preview-page">
                <h4>Page 2</h4>
                <p>{projectData.discovery?.business_problem || <em style={{ color: '#aaa' }}>No business problem</em>}</p>
                <p>{projectData.discovery?.business_goals || <em style={{ color: '#aaa' }}>No business goals</em>}</p>
              </div>
              <div className="preview-page">
                <h4>Page 3</h4>
                <p>
                  Requirements:{' '}
                  {projectData.functional_requirements && projectData.functional_requirements.length > 0 ? (
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
          {projectData.functional_requirements && projectData.functional_requirements.length > 0 ? (
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
          {projectData.missing_fields && projectData.missing_fields.length > 0 ? (
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
    <div className="page centered-page" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '16px' }}>
      <button 
        className="secondary" 
        onClick={() => setActivePage('dashboard')}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', fontSize: '0.9rem' }}
      >
        ⬅ Back to Dashboard
      </button>
      <section className="page export-card" style={{ width: '100%' }}>
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
