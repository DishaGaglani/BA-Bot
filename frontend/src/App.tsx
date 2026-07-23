import { useEffect, useState, useRef, type FormEvent, type ChangeEvent } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import './App.css'
import AdminPortal from './admin/AdminPortal'

type PageView = 'dashboard' | 'new-project' | 'interview' | 'review' | 'export' | 'admin'
type MessageRole = 'ai' | 'user'
type UpdateSection = 'project' | 'overview' | 'discovery'

// User Roles
type UserRole = 'SUPER_ADMIN' | 'ADMIN' | 'BUSINESS_ANALYST' | 'PROJECT_MANAGER' | 'VIEWER' | 'REVIEWER' | 'CLIENT'
// Project Member Roles
type ProjectMemberRole = 'OWNER' | 'EDITOR' | 'VIEWER'

interface User {
  id: number
  name: string
  email: string
  role: UserRole
}

interface ProjectMember {
  id: number
  user_id: number
  name: string
  email: string
  role: ProjectMemberRole
}

interface Requirement {
  title: string
  priority: string
  confidence: number
}

interface ProjectData {
  id?: number
  owner_id?: number
  status?: string // 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED'
  sessionId?: string | null
  pdfGenerated?: boolean
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
  owner_id: undefined,
  status: 'DRAFT',
  sessionId: null,
  pdfGenerated: false,
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

const sanitizeProjectData = (data: any): ProjectData => {
  return {
    id: data?.id,
    owner_id: data?.owner_id,
    status: data?.status || 'DRAFT',
    sessionId: data?.sessionId || null,
    pdfGenerated: data?.pdfGenerated || false,
    messages: data?.messages || initialMessages,
    project: {
      name: data?.project?.name || '',
      department: data?.project?.department || '',
      sponsor: data?.project?.sponsor || '',
      business_unit: data?.project?.business_unit || '',
      expected_completion: data?.project?.expected_completion || '',
    },
    overview: {
      description: data?.overview?.description || '',
      stakeholders: data?.overview?.stakeholders || [],
    },
    discovery: {
      business_problem: data?.discovery?.business_problem || '',
      business_goals: data?.discovery?.business_goals || '',
      desired_outcomes: data?.discovery?.desired_outcomes || '',
      constraints: data?.discovery?.constraints || '',
    },
    functional_requirements: data?.functional_requirements || [],
    missing_fields: data?.missing_fields || [],
    next_question: data?.next_question || '',
  }
}

function extractFieldsFromChat(messages: Message[]): Partial<ProjectData> | null {
  const summaryMsg = [...messages].reverse().find(
    (m) => m.role === 'ai' && m.text.includes('Requirement Discovery Summary')
  );
  
  const updates: any = {
    project: {},
    overview: {},
    discovery: {},
    functional_requirements: []
  };
  
  let foundAny = false;
  
  if (summaryMsg) {
    const text = summaryMsg.text;
    
    const descMatch = text.match(/^\s*[-*+]\s*\*\*(?:Description|Project Overview|Overview):\*\*\s*(.*)$/im) || 
                      text.match(/\*\*(?:Description|Project Overview|Overview):\*\*\s*(.*)/i);
    if (descMatch) {
      updates.overview.description = descMatch[1].trim();
      foundAny = true;
    }
    
    const problemMatch = text.match(/^\s*[-*+]\s*\*\*(?:Business Problem|Problem):\*\*\s*(.*)$/im) || 
                         text.match(/\*\*(?:Business Problem|Problem):\*\*\s*(.*)/i);
    if (problemMatch) {
      updates.discovery.business_problem = problemMatch[1].trim();
      foundAny = true;
    }
    
    const goalsMatch = text.match(/^\s*[-*+]\s*\*\*(?:Business Goals|Goals):\*\*\s*(.*)$/im) || 
                       text.match(/\*\*(?:Business Goals|Goals):\*\*\s*(.*)/i);
    if (goalsMatch) {
      updates.discovery.business_goals = goalsMatch[1].trim();
      foundAny = true;
    }
    
    const constraintsMatch = text.match(/^\s*[-*+]\s*\*\*(?:Constraints|NFR|Non-Functional Requirements):\*\*\s*(.*)$/im) || 
                             text.match(/\*\*(?:Constraints|NFR|Non-Functional Requirements):\*\*\s*(.*)/i);
    if (constraintsMatch) {
      updates.discovery.constraints = constraintsMatch[1].trim();
      foundAny = true;
    }

    const outcomesMatch = text.match(/^\s*[-*+]\s*\*\*(?:Desired Outcomes|Outcomes):\*\*\s*(.*)$/im) || 
                          text.match(/\*\*(?:Desired Outcomes|Outcomes):\*\*\s*(.*)/i);
    if (outcomesMatch) {
      updates.discovery.desired_outcomes = outcomesMatch[1].trim();
      foundAny = true;
    }
    
    const funcMatch = text.match(/^\s*[-*+]\s*\*\*(?:Features|Functional Requirements|Requirements):\*\*\s*(.*)$/im) ||
                      text.match(/\*\*(?:Features|Functional Requirements|Requirements):\*\*\s*(.*)/i);
    if (funcMatch) {
      const listStr = funcMatch[1].trim();
      const items = listStr.split(/,|\*|-/).map(s => s.trim()).filter(Boolean);
      if (items.length > 0) {
        updates.functional_requirements = items.map((title) => ({
          title,
          priority: 'High',
          confidence: 1.0
        }));
        foundAny = true;
      }
    }
  }

  const hasDownloadLink = messages.some(
    (m) => m.role === 'ai' && (m.text.includes('.docx') || m.text.includes('.pdf')) && m.text.includes('](')
  );
  if (hasDownloadLink) {
    updates.pdfGenerated = true;
    foundAny = true;
  }
  
  return foundAny ? updates : null;
}

function parseInlineMarkdown(text: string): React.ReactNode {
  const inlineRegex = /(\*\*.*?\*\*|`.*?`|\[.*?\]\(.*?\))/g;
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
    if (part.startsWith('[') && part.includes('](') && part.endsWith(')')) {
      const match = part.match(/\[(.*?)\]\((.*?)\)/);
      if (match) {
        const label = match[1];
        let url = match[2];
        
        if (url.includes('29fc96e-5b62-4208-8787-0d77367e9eaf')) {
          url = url.replace('29fc96e-5b62-4208-8787-0d77367e9eaf', '249fc96e-5b62-4208-8787-0d77367e9eaf');
        }
        
        return (
          <a
            key={index}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: '#3755d4',
              textDecoration: 'underline',
            }}
          >
            {label}
          </a>
        );
      }
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
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('ba_bot_token'))
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  
  // Auth Form State
  const [authTab, setAuthTab] = useState<'login' | 'register' | 'admin' | 'admin_register'>('login')
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regRole, setRegRole] = useState<UserRole>('BUSINESS_ANALYST')
  const [authError, setAuthError] = useState('')

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

  // Project Members lists
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<ProjectMemberRole>('EDITOR')
  
  // Feedback from Reviewer
  const [reviewerFeedback, setReviewerFeedback] = useState('')

  // Workspace tab & details state
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<'details' | 'overview' | 'discovery' | 'requirements' | 'members'>('details')

  const handleAddRequirement = () => {
    setProjectData((prev) => {
      const prevReqs = prev.functional_requirements || []
      return {
        ...prev,
        functional_requirements: [
          ...prevReqs,
          { title: 'New requirement title', priority: 'Medium', confidence: 1.0 }
        ]
      }
    })
  }

  const handleUpdateRequirement = (index: number, key: 'title' | 'priority' | 'confidence', value: any) => {
    setProjectData((prev) => {
      const list = [...(prev.functional_requirements || [])]
      if (list[index]) {
        list[index] = {
          ...list[index],
          [key]: value
        }
      }
      return {
        ...prev,
        functional_requirements: list
      }
    })
  }

  const handleDeleteRequirement = (index: number) => {
    setProjectData((prev) => {
      const list = [...(prev.functional_requirements || [])]
      list.splice(index, 1)
      return {
        ...prev,
        functional_requirements: list
      }
    })
  }

  // Admin panel state
  const [adminTab, setAdminTab] = useState<'users' | 'logs'>('users')
  const [usersList, setUsersList] = useState<any[]>([])
  const [logsList, setLogsList] = useState<any[]>([])
  const [adminNewName, setAdminNewName] = useState('')
  const [adminNewEmail, setAdminNewEmail] = useState('')
  const [adminNewPassword, setAdminNewPassword] = useState('')
  const [adminNewRole, setAdminNewRole] = useState<UserRole>('BUSINESS_ANALYST')

  const messageListRef = useRef<HTMLDivElement | null>(null)

  const chatMessages = projectData.messages || initialMessages
  const currentSessionId = projectData.sessionId || null

  const calculateCompletion = (proj: ProjectData) => {
    const hasProjectName = proj.project?.name;
    const hasOverviewDesc = proj.overview?.description;
    const hasDiscoveryProblem = proj.discovery?.business_problem;
    const hasDiscoveryGoals = proj.discovery?.business_goals;
    const hasFunctionalReqs = proj.functional_requirements && proj.functional_requirements.length > 0;
    const hasPdf = proj.pdfGenerated;
    
    return Math.round(
      (Number(Boolean(hasProjectName)) +
        Number(Boolean(hasOverviewDesc)) +
        Number(Boolean(hasDiscoveryProblem)) +
        Number(Boolean(hasDiscoveryGoals)) +
        Number(Boolean(hasFunctionalReqs)) +
        Number(Boolean(hasPdf))) /
        6 *
        100,
    )
  }

  // Determine current user's role on active project
  const getCurrentProjectRole = (): ProjectMemberRole | null => {
    if (!currentUser) return null
    if (currentUser.role === 'ADMIN') return 'OWNER'
    if (projectData.owner_id === currentUser.id) return 'OWNER'
    
    const member = projectMembers.find(m => m.user_id === currentUser.id)
    return member ? member.role : null
  }

  const projectRole = getCurrentProjectRole()

  const loadProjects = async (authToken = token) => {
    if (!authToken) return []
    try {
      const response = await fetch('http://127.0.0.1:8000/api/projects', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      })
      if (response.ok) {
        const list = await response.json()
        setProjectsList(list)
        return list
      } else if (response.status === 401) {
        handleLogout()
      }
    } catch (error) {
      console.error('Failed to load projects list', error)
    }
    return []
  }

  const handleLoadProject = async (id: number) => {
    if (!token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const proj = await response.json()
        setActiveProjectId(id)
        localStorage.setItem('ba_bot_active_project_id', id.toString())
        setProjectData(sanitizeProjectData(proj))
        setActivePage('interview')
        void loadProjectMembers(id)
      } else if (response.status === 401) {
        handleLogout()
      } else if (response.status === 403) {
        alert("You do not have access to this project.")
      }
    } catch (error) {
      console.error('Failed to load project details', error)
    }
  }

  const loadProjectMembers = async (projId: number) => {
    if (!token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${projId}/members`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const list = await response.json()
        setProjectMembers(list)
      }
    } catch (error) {
      console.error('Failed to load project members', error)
    }
  }

  const handleDeleteProject = async (id: number) => {
    if (!confirm('Are you sure you want to delete this project?')) return
    if (!token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
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
      } else {
        alert("Only the project owner or an Administrator can delete this project.")
      }
    } catch (error) {
      console.error('Failed to delete project', error)
    }
  }

  const handleInviteMember = async (e: FormEvent) => {
    e.preventDefault()
    if (!activeProjectId || !inviteEmail.trim() || !token) return
    
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}/invite`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole })
      })
      
      if (response.ok) {
        const data = await response.json()
        setNotice({ title: 'User Invited', detail: data.message })
        setInviteEmail('')
        void loadProjectMembers(activeProjectId)
        setTimeout(() => setNotice(null), 1800)
      } else {
        const err = await response.json()
        alert(err.detail || "Failed to invite user.")
      }
    } catch (error) {
      console.error("Failed to invite member", error)
    }
  }

  const handleSubmitForReview = async () => {
    if (!activeProjectId || !token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}/submit`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setProjectData(prev => ({ ...prev, status: data.new_status }))
        setNotice({ title: 'Project Submitted', detail: 'Project is now under review.' })
        setTimeout(() => setNotice(null), 1800)
      }
    } catch (error) {
      console.error("Failed to submit project", error)
    }
  }

  const handleReviewProject = async (approved: boolean) => {
    if (!activeProjectId || !token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}/review`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ approved, feedback: reviewerFeedback })
      })
      if (response.ok) {
        const data = await response.json()
        setProjectData(prev => ({ ...prev, status: data.new_status }))
        setReviewerFeedback('')
        setNotice({ 
          title: approved ? 'Project Approved' : 'Project Rejected', 
          detail: approved ? 'Requirements document marked as approved!' : 'Project returned to Business Analyst.' 
        })
        setTimeout(() => setNotice(null), 1800)
      } else {
        alert("Failed to review project.")
      }
    } catch (error) {
      console.error("Failed to review project", error)
    }
  }

  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight
    }
  }, [chatMessages])

  const handleAutoCreateProject = async (authToken = token) => {
    if (!authToken) return null
    try {
      const response = await fetch('http://127.0.0.1:8000/api/projects', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          project: {
            name: "Discovery Session",
            department: "",
            sponsor: "",
            business_unit: "",
            expected_completion: ""
          },
          overview: {},
          discovery: {},
          functional_requirements: [],
          missing_fields: [],
          next_question: ""
        })
      })
      if (response.ok) {
        const newProj = await response.json()
        setProjectsList([newProj])
        setActiveProjectId(newProj.id)
        localStorage.setItem('ba_bot_active_project_id', newProj.id.toString())
        setProjectData(sanitizeProjectData(newProj))
        setActivePage('interview')
        void loadProjectMembers(newProj.id)
        return newProj
      }
    } catch (err) {
      console.error("Auto-create project failed", err)
    }
    return null
  }

  const fetchAdminData = async () => {
    if (!token) return
    try {
      const uRes = await fetch('http://127.0.0.1:8000/api/admin/users', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (uRes.ok) {
        setUsersList(await uRes.json())
      }
      
      const lRes = await fetch('http://127.0.0.1:8000/api/admin/audit-logs', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (lRes.ok) {
        setLogsList(await lRes.json())
      }
    } catch (e) {
      console.error("Failed to load admin data", e)
    }
  }

  const handleUpdateUserRole = async (userId: number, newRole: string) => {
    if (!token) return
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/admin/users/${userId}/role`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ role: newRole })
      })
      if (response.ok) {
        setNotice({ title: "Role Updated", detail: `User role was successfully updated to ${newRole}.` })
        setTimeout(() => setNotice(null), 1800)
        await fetchAdminData()
      } else {
        const err = await response.json()
        alert(err.detail || "Failed to update role.")
      }
    } catch (e) {
      console.error("Failed to update role", e)
    }
  }

  const handleCreateUserByAdmin = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return
    if (!adminNewName || !adminNewEmail || !adminNewPassword) {
      alert("Please fill in all user details.")
      return
    }
    try {
      const response = await fetch('http://127.0.0.1:8000/api/admin/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: adminNewName,
          email: adminNewEmail,
          password: adminNewPassword,
          role: adminNewRole
        })
      })
      if (response.ok) {
        setNotice({ title: "User Added", detail: `Successfully created user ${adminNewName} with role ${adminNewRole}` })
        setTimeout(() => setNotice(null), 1800)
        setAdminNewName('')
        setAdminNewEmail('')
        setAdminNewPassword('')
        setAdminNewRole('BUSINESS_ANALYST')
        await fetchAdminData()
      } else {
        const err = await response.json()
        alert(err.detail || "Failed to create user.")
      }
    } catch (e) {
      console.error("Failed to add user", e)
    }
  }

  useEffect(() => {
    if (activePage === 'admin') {
      void fetchAdminData()
    }
  }, [activePage])

  // Profile and Initial setup
  useEffect(() => {
    const fetchProfileAndProjects = async () => {
      if (!token) {
        // If not logged in and requesting /admin, keep user on login page
        setIsLoaded(true)
        return
      }
      try {
        const response = await fetch('http://127.0.0.1:8000/api/auth/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (response.ok) {
          const user = await response.json()
          setCurrentUser(user)
          const list = await loadProjects(token)
          setIsLoaded(true)
          
          if (activeProjectId) {
            const found = list.find((p: ProjectData) => p.id === activeProjectId)
            if (found) {
              setProjectData(sanitizeProjectData(found))
              void loadProjectMembers(activeProjectId)
            } else {
              setActiveProjectId(null)
              localStorage.removeItem('ba_bot_active_project_id')
            }
          }
          
          // Path routing protection
          if (window.location.pathname === '/admin') {
            if (user.role === 'SUPER_ADMIN' || user.role === 'ADMIN') {
              setActivePage('admin')
            } else {
              // Redirect non-admins to dashboard
              setActivePage('dashboard')
              window.history.replaceState({}, '', '/')
            }
          } else {
            setActivePage('dashboard')
          }
        } else {
          handleLogout()
          setIsLoaded(true)
        }
      } catch (error) {
        console.error('Failed initialization', error)
        setIsLoaded(true)
      }
    }
    void fetchProfileAndProjects()
  }, [token])

  // Sync state with browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname
      if (path === '/admin') {
        if (currentUser && (currentUser.role === 'SUPER_ADMIN' || currentUser.role === 'ADMIN')) {
          setActivePage('admin')
        } else {
          setActivePage('dashboard')
          window.history.replaceState({}, '', '/')
        }
      } else {
        setActivePage('dashboard')
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [currentUser])

  // Sync details on edit
  useEffect(() => {
    if (!isLoaded || !activeProjectId || projectData.id !== activeProjectId || !token) return

    const syncProjectData = async () => {
      try {
        await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}`, {
          method: 'PUT',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
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
  }, [projectData, activeProjectId, isLoaded, token])

  useEffect(() => {
    if (!projectData.messages || projectData.messages.length === 0) return;
    
    const extracted = extractFieldsFromChat(projectData.messages);
    if (extracted) {
      setProjectData((prev) => {
        let changed = false;
        const newOverview = { ...prev.overview };
        const newDiscovery = { ...prev.discovery };
        let newFuncReqs = prev.functional_requirements ? [...prev.functional_requirements] : [];
        let newPdfGenerated = prev.pdfGenerated;

        if (extracted.overview?.description && prev.overview?.description !== extracted.overview.description) {
          newOverview.description = extracted.overview.description;
          changed = true;
        }
        if (extracted.discovery?.business_problem && prev.discovery?.business_problem !== extracted.discovery.business_problem) {
          newDiscovery.business_problem = extracted.discovery.business_problem;
          changed = true;
        }
        if (extracted.discovery?.business_goals && prev.discovery?.business_goals !== extracted.discovery.business_goals) {
          newDiscovery.business_goals = extracted.discovery.business_goals;
          changed = true;
        }
        if (extracted.discovery?.constraints && prev.discovery?.constraints !== extracted.discovery.constraints) {
          newDiscovery.constraints = extracted.discovery.constraints;
          changed = true;
        }
        if (extracted.discovery?.desired_outcomes && prev.discovery?.desired_outcomes !== extracted.discovery.desired_outcomes) {
          newDiscovery.desired_outcomes = extracted.discovery.desired_outcomes;
          changed = true;
        }
        if (extracted.functional_requirements && extracted.functional_requirements.length > 0 && (!prev.functional_requirements || prev.functional_requirements.length === 0)) {
          newFuncReqs = extracted.functional_requirements;
          changed = true;
        }
        if (extracted.pdfGenerated && !prev.pdfGenerated) {
          newPdfGenerated = true;
          changed = true;
        }

        if (changed) {
          return {
            ...prev,
            overview: newOverview,
            discovery: newDiscovery,
            functional_requirements: newFuncReqs,
            pdfGenerated: newPdfGenerated,
          };
        }
        return prev;
      });
    }
  }, [projectData.messages])

  const completion = Math.round(
    (Number(Boolean(projectData.project?.name)) +
      Number(Boolean(projectData.overview?.description)) +
      Number(Boolean(projectData.discovery?.business_problem)) +
      Number(Boolean(projectData.discovery?.business_goals)) +
      Number((projectData.functional_requirements?.length || 0) > 0) +
      Number(Boolean(projectData.pdfGenerated))) /
      6 *
      100,
  )

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const incoming = draftInput.trim()
    if (!incoming || !token) return

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
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
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
                  const meta = parsed.data as { sessionId?: string; chatId?: string }
                  const activeSessionId = meta.chatId || meta.sessionId
                  if (activeSessionId) {
                    setProjectData((prev) => ({
                      ...prev,
                      sessionId: activeSessionId,
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

      if (activeProjectId && token) {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
          })
          if (res.ok) {
            const updatedProject = await res.json()
            setProjectData(sanitizeProjectData(updatedProject))
          }
        } catch (err) {
          console.error("Failed to sync final stream state", err)
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

  const updateField = (section: UpdateSection, key: string, value: any) => {
    setProjectData((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] as Record<string, any>),
        [key]: value,
      },
    }))
  }

  const handleStartNewInterview = async () => {
    if (!token) return
    const newProjPayload: ProjectData = {
      ...projectData,
      messages: initialMessages,
      sessionId: null,
    }

    try {
      setIsLoading(true)
      const response = await fetch('http://127.0.0.1:8000/api/projects', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newProjPayload),
      })
      
      if (response.ok) {
        const createdProj = await response.json()
        const newId = createdProj.id
        
        setActiveProjectId(newId)
        localStorage.setItem('ba_bot_active_project_id', newId.toString())
        setProjectData(sanitizeProjectData(createdProj))
        
        await loadProjects(token)
        setActivePage('interview')
        void loadProjectMembers(newId)
      }
    } catch (error) {
      console.error('Failed to create new project', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleClearConversation = async () => {
    if (!activeProjectId || !token) return;
    if (!confirm('Are you sure you want to clear the conversation history?')) return;
    
    const updatedProject = {
      ...projectData,
      messages: initialMessages,
      sessionId: null,
    };
    setProjectData(updatedProject);

    try {
      await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
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
      if (action.includes('Overview')) {
        setActiveWorkspaceTab('overview')
      } else if (action.includes('Discovery')) {
        setActiveWorkspaceTab('discovery')
      } else if (action.includes('Requirements')) {
        setActiveWorkspaceTab('requirements')
      }
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
        const response = await fetch(`http://127.0.0.1:8000/api/projects/${activeProjectId}/export?format=${format}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        
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
        
        setProjectData((prev) => ({
          ...prev,
          pdfGenerated: true,
        }))
        
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

  // Authentication logic handlers
  const handleLoginSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setAuthError('')
    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword })
      })
      if (response.ok) {
        const data = await response.json()
        localStorage.setItem('ba_bot_token', data.access_token)
        setToken(data.access_token)
        setCurrentUser(data.user)
        setLoginEmail('')
        setLoginPassword('')
        
        // Handle admin automatic routing redirect
        if (data.user.role === 'SUPER_ADMIN' || data.user.role === 'ADMIN') {
          setActivePage('admin')
          window.history.pushState({}, '', '/admin')
        } else {
          setActivePage('dashboard')
          if (window.location.pathname === '/admin') {
            window.history.replaceState({}, '', '/')
          }
        }
        
        setNotice({ title: 'Welcome Back', detail: `Successfully signed in as ${data.user.name}` })
        setTimeout(() => setNotice(null), 1800)
      } else {
        const err = await response.json()
        setAuthError(err.detail || "Authentication failed. Check credentials.")
      }
    } catch (e) {
      setAuthError("Server is unreachable. Make sure the backend is running.")
    }
  }

  const handleRegisterSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setAuthError('')
    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: regName, email: regEmail, password: regPassword, role: regRole })
      })
      if (response.ok) {
        setNotice({ title: 'Registration Complete', detail: 'Account created! Logging in now...' })
        // Autologin after registration
        const loginRes = await fetch('http://127.0.0.1:8000/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: regEmail, password: regPassword })
        })
        if (loginRes.ok) {
          const data = await loginRes.json()
          localStorage.setItem('ba_bot_token', data.access_token)
          setToken(data.access_token)
          setCurrentUser(data.user)
          setRegName('')
          setRegEmail('')
          setRegPassword('')
          
          if (data.user.role === 'SUPER_ADMIN' || data.user.role === 'ADMIN') {
            setActivePage('admin')
            window.history.pushState({}, '', '/admin')
          } else {
            setActivePage('dashboard')
            if (window.location.pathname === '/admin') {
              window.history.replaceState({}, '', '/')
            }
          }
        }
        setTimeout(() => setNotice(null), 1800)
      } else {
        const err = await response.json()
        setAuthError(err.detail || "Registration failed. Verify fields.")
      }
    } catch (e) {
      setAuthError("Connection refused by server.")
    }
  }

  const handleLogout = async () => {
    if (token) {
      try {
        await fetch('http://127.0.0.1:8000/api/auth/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        })
      } catch (e) {}
    }
    localStorage.removeItem('ba_bot_token')
    localStorage.removeItem('ba_bot_active_project_id')
    setToken(null)
    setCurrentUser(null)
    setActiveProjectId(null)
    setProjectData(initialProject)
    setProjectsList([])
    setActivePage('dashboard')
    window.history.pushState({}, '', '/')
  }

  const getStatusColor = (status: string = 'DRAFT') => {
    switch (status) {
      case 'APPROVED': return '#10b981';
      case 'IN_REVIEW': return '#f59e0b';
      case 'REJECTED': return '#ef4444';
      default: return '#64748b';
    }
  }

  const getRoleLabel = (role: UserRole) => {
    switch (role) {
      case 'SUPER_ADMIN': return 'Super Admin';
      case 'ADMIN': return 'Administrator';
      case 'BUSINESS_ANALYST': return 'Business Analyst';
      case 'PROJECT_MANAGER': return 'Project Manager';
      case 'VIEWER': return 'Viewer';
      case 'REVIEWER': return 'Review Committee';
      default: return role;
    }
  }

  // --- RENDERS ---

  const renderAuthPage = () => {
    return (
      <div className="auth-split-wrapper">
        {/* Left Branding Side (Desktop Only) */}
        <div className="auth-branding-side">
          <div className="branding-header">
            <span style={{ fontSize: '2rem' }}>🤖</span>
            <div className="branding-logo">BA Bot</div>
          </div>
          
          <div className="branding-content">
            <h1>Requirements Discovery Workspace</h1>
            <p>
              Leverage deterministic gap analysis and intelligent conversational workflows to capture, validate, and compile project requirements.
            </p>
            
            <div className="feature-bullets">
              <div className="feature-bullet">
                <div className="feature-bullet-icon">💬</div>
                <div className="feature-bullet-text">
                  <strong>Intelligent Chatbot Discovery</strong>
                  <span>Guided conversational agent that dynamically identifies missing information.</span>
                </div>
              </div>
              
              <div className="feature-bullet">
                <div className="feature-bullet-icon">⚙️</div>
                <div className="feature-bullet-text">
                  <strong>Structured State Sync</strong>
                  <span>Interactive forms capture details in real-time, syncing automatically with our backend.</span>
                </div>
              </div>
              
              <div className="feature-bullet">
                <div className="feature-bullet-icon">👥</div>
                <div className="feature-bullet-text">
                  <strong>Project Collaboration</strong>
                  <span>Invite teammates with granular roles (Viewer/Editor) to audit and refine scope.</span>
                </div>
              </div>
              
              <div className="feature-bullet">
                <div className="feature-bullet-icon">📄</div>
                <div className="feature-bullet-text">
                  <strong>Compliance Exports</strong>
                  <span>Generate professional, client-ready requirements documentation in Word and PDF formats.</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="branding-footer">
            <span>© 2026 BA Bot Enterprise</span>
            <span>v1.0.0</span>
          </div>
        </div>
        
        {/* Right Form Side */}
        <div className="auth-form-side">
          <div className={`auth-card-container ${authTab === 'admin' || authTab === 'admin_register' ? 'admin-portal-mode' : ''}`}>
            {/* Tabs header */}
            <div className="auth-tabs">
              <button 
                onClick={() => { setAuthTab('login'); setAuthError('') }}
                className={`auth-tab-btn ${authTab === 'login' ? 'active' : ''}`}
              >
                Sign In
              </button>
              <button 
                onClick={() => { setAuthTab('register'); setRegRole('BUSINESS_ANALYST'); setAuthError('') }}
                className={`auth-tab-btn ${authTab === 'register' ? 'active' : ''}`}
              >
                Register
              </button>
              <button 
                onClick={() => { setAuthTab('admin'); setAuthError('') }}
                className={`auth-tab-btn ${authTab === 'admin' || authTab === 'admin_register' ? 'active' : ''}`}
              >
                Admin Portal 🛡️
              </button>
            </div>

            {/* Form body */}
            <div style={{ padding: '32px' }}>
              <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                <h2 style={{ margin: '0 0 6px 0', fontSize: '1.5rem', color: 'var(--dark-slate)' }}>
                  {authTab === 'admin' || authTab === 'admin_register' ? 'Control Console' : 'BA Workspace'}
                </h2>
                <p style={{ margin: '0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  {authTab === 'admin' || authTab === 'admin_register'
                    ? 'Authorized Administrative Access Only' 
                    : 'Enterprise Requirement Discovery Portal'}
                </p>
              </div>

              {authError && (
                <div style={{
                  background: 'var(--danger-light)',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  color: 'var(--danger)',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  fontSize: '0.85rem',
                  marginBottom: '20px',
                  fontWeight: '500'
                }}>
                  ⚠️ {authError}
                </div>
              )}

              {(authTab === 'admin' || authTab === 'admin_register') && (
                <div className="admin-warning-box">
                  <strong>SYSTEM SECURITY NOTICE:</strong> All authentication attempts, system settings changes, and audit log accesses are strictly monitored and recorded.
                </div>
              )}

              {authTab === 'admin' && (
                <div className="admin-helper-credentials">
                  <strong>Admin Developer Seed Credentials:</strong><br />
                  Email: <code style={{ userSelect: 'all', fontWeight: 'bold' }}>admin@example.com</code><br />
                  Password: <code style={{ userSelect: 'all', fontWeight: 'bold' }}>admin123</code>
                </div>
              )}

              {authTab === 'login' || authTab === 'admin' ? (
                <form onSubmit={handleLoginSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <label>
                    Email Address
                    <input 
                      type="email" 
                      value={loginEmail} 
                      onChange={e => setLoginEmail(e.target.value)} 
                      required 
                      placeholder={authTab === 'admin' ? "admin@example.com" : "name@company.com"}
                    />
                  </label>

                  <label>
                    Password
                    <input 
                      type="password" 
                      value={loginPassword} 
                      onChange={e => setLoginPassword(e.target.value)} 
                      required 
                      placeholder="••••••••"
                    />
                  </label>

                  <button type="submit" className={authTab === 'admin' ? 'danger' : 'primary'} style={{
                    padding: '12px',
                    fontSize: '0.95rem',
                    marginTop: '12px',
                    width: '100%'
                  }}>
                    {authTab === 'admin' ? 'Enter Control Console 🛡️' : 'Sign In to Workspace'}
                  </button>

                  {authTab === 'admin' && (
                    <div style={{ marginTop: '16px', textAlign: 'center', fontSize: '0.85rem', color: '#64748b' }}>
                      Don't have an admin account?{' '}
                      <a 
                        onClick={() => { setAuthTab('admin_register'); setRegRole('ADMIN'); setAuthError('') }}
                        style={{ color: '#ef4444', fontWeight: '700', cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        Register Admin
                      </a>
                    </div>
                  )}
                </form>
              ) : (
                <form onSubmit={handleRegisterSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <label>
                    Full Name
                    <input 
                      type="text" 
                      value={regName} 
                      onChange={e => setRegName(e.target.value)} 
                      required 
                      placeholder="John Doe"
                    />
                  </label>

                  <label>
                    Email Address
                    <input 
                      type="email" 
                      value={regEmail} 
                      onChange={e => setRegEmail(e.target.value)} 
                      required 
                      placeholder="name@company.com"
                    />
                  </label>

                  <label>
                    Password
                    <input 
                      type="password" 
                      value={regPassword} 
                      onChange={e => setRegPassword(e.target.value)} 
                      required 
                      placeholder="••••••••"
                    />
                  </label>

                  {authTab === 'admin_register' && (
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.9rem', fontWeight: '600' }}>
                      Admin System Role
                      <select 
                        value={regRole} 
                        onChange={e => setRegRole(e.target.value as UserRole)}
                        style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', cursor: 'pointer', backgroundColor: '#fff' }}
                      >
                        <option value="ADMIN">ADMIN</option>
                        <option value="SUPER_ADMIN">SUPER_ADMIN</option>
                        <option value="PROJECT_MANAGER">PROJECT_MANAGER</option>
                        <option value="VIEWER">VIEWER</option>
                        <option value="REVIEWER">REVIEWER</option>
                      </select>
                    </label>
                  )}

                  <button type="submit" className={authTab === 'admin_register' ? 'danger' : 'primary'} style={{
                    padding: '12px',
                    fontSize: '0.95rem',
                    marginTop: '12px',
                    width: '100%'
                  }}>
                    {authTab === 'admin_register' ? 'Create Admin Account 🛡️' : 'Create Account'}
                  </button>

                  {authTab === 'admin_register' && (
                    <div style={{ marginTop: '16px', textAlign: 'center', fontSize: '0.85rem', color: '#64748b' }}>
                      Already have an admin account?{' '}
                      <a 
                        onClick={() => { setAuthTab('admin'); setAuthError('') }}
                        style={{ color: '#ef4444', fontWeight: '700', cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        Sign In
                      </a>
                    </div>
                  )}
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const renderDashboard = () => {
    const totalProjects = projectsList.length
    const completedProjects = projectsList.filter(p => calculateCompletion(p) === 100).length
    const pendingProjects = totalProjects - completedProjects
    const hoursSaved = completedProjects * 6

    const canCreate = currentUser && (currentUser.role === 'ADMIN' || currentUser.role === 'BUSINESS_ANALYST' || currentUser.role === 'REVIEWER')

    return (
      <div className="dashboard-layout" style={{ display: 'flex', flexDirection: 'column', gap: '32px', width: '100%' }}>
        <section className="page">
          <div className="section-heading">
            <h2>Projects</h2>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <span className="badge">{totalProjects} active</span>
              {canCreate && (
                <button className="primary" onClick={handleStartNewInterview} style={{ padding: '6px 14px', fontSize: '0.85rem' }}>
                  + New Project
                </button>
              )}
            </div>
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
            {canCreate && (
              <article 
                className="project-tile plus-tile" 
                onClick={handleStartNewInterview}
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
                <span style={{ fontWeight: '600', color: '#4b5c77', marginTop: '12px' }}>Add Project</span>
              </article>
            )}

            {projectsList.map((p) => {
              const comp = calculateCompletion(p);
              const isOwner = currentUser && (p.owner_id === currentUser.id || currentUser.role === 'ADMIN');
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
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                      <h3 style={{ margin: '0', fontSize: '1.2rem', color: '#1e293b', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.project?.name || 'Untitled Project'}
                      </h3>
                      <span style={{
                        fontSize: '0.7rem',
                        fontWeight: '700',
                        padding: '3px 8px',
                        borderRadius: '6px',
                        background: `${getStatusColor(p.status)}22`,
                        color: getStatusColor(p.status)
                      }}>
                        {p.status || 'DRAFT'}
                      </span>
                    </div>
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
                  
                  {isOwner && (
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
                  )}
                </article>
              );
            })}

            {projectsList.length === 0 && (
              <div style={{ gridColumn: '1 / -1', padding: '48px', textAlign: 'center', color: '#64748b' }}>
                <p>No active projects found. Get started by creating a new project interview workshop.</p>
              </div>
            )}
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
              value={projectData.project?.name || ''}
              placeholder="Enter project name"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'name', event.target.value)}
            />
          </label>
          <label>
            Department
            <input
              value={projectData.project?.department || ''}
              placeholder="Enter department"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'department', event.target.value)}
            />
          </label>
          <label>
            Business Unit
            <input
              value={projectData.project?.business_unit || ''}
              placeholder="Enter business unit"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'business_unit', event.target.value)}
            />
          </label>
          <label>
            Project Sponsor
            <input
              value={projectData.project?.sponsor || ''}
              placeholder="Enter sponsor name"
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField('project', 'sponsor', event.target.value)}
            />
          </label>
          <label>
            Expected Completion
            <input
              value={projectData.project?.expected_completion || ''}
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

  const renderInterview = () => {
    const isViewer = projectRole === 'VIEWER'
    const isOwnerOrAdmin = currentUser && (projectData.owner_id === currentUser.id || currentUser.role === 'ADMIN')
    
    // Status banners
    const isApproved = projectData.status === 'APPROVED'
    const isInReview = projectData.status === 'IN_REVIEW'
    const isLocked = isViewer || isApproved || isInReview
    
    return (
      <div className="interview-shell">
        {/* Sub-header Bar */}
        <div className="panel-header interview-header" style={{ borderLeft: `6px solid ${getStatusColor(projectData.status)}`, padding: '12px 24px', background: '#ffffff', borderRadius: '12px', boxShadow: 'var(--shadow-sm)' }}>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <button 
              className="secondary" 
              onClick={() => setActivePage('dashboard')}
              style={{ padding: '8px 14px', fontSize: '0.9rem' }}
            >
              📋 All Projects
            </button>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <p className="eyebrow" style={{ margin: '0' }}>AI Workspace</p>
                <span style={{
                  fontSize: '0.75rem',
                  fontWeight: '700',
                  padding: '2px 8px',
                  borderRadius: '6px',
                  background: `${getStatusColor(projectData.status)}22`,
                  color: getStatusColor(projectData.status)
                }}>
                  {projectData.status}
                </span>
              </div>
              <h2 style={{ marginTop: '4px', fontSize: '1.4rem' }}>{projectData.project?.name || 'Discovery Workshop'}</h2>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
            {projectData.status === 'DRAFT' && isOwnerOrAdmin && (
              <button className="primary" style={{ backgroundColor: '#f59e0b', boxShadow: '0 4px 12px rgba(245, 158, 11, 0.2)' }} onClick={handleSubmitForReview}>
                Submit for Review
              </button>
            )}
            <button className="secondary" onClick={() => setActivePage('review')}>
              Go to Review &amp; Export
            </button>
            {(currentUser?.role === 'SUPER_ADMIN' || currentUser?.role === 'ADMIN') && (
              <button 
                className="secondary" 
                onClick={() => {
                  setActivePage('admin')
                  window.history.pushState({}, '', '/admin')
                }} 
                style={{ fontSize: '0.85rem', padding: '8px 16px', background: '#eff6ff', color: '#1e40af', border: '1px solid #bfdbfe' }}
              >
                🛡️ Admin Panel
              </button>
            )}
            <div className="profile-pill">
              <span style={{ fontSize: '0.85rem', fontWeight: '700', color: '#1e293b' }}>{currentUser?.name}</span>
              <span style={{ fontSize: '0.7rem', fontWeight: '700', color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {currentUser && getRoleLabel(currentUser.role)}
              </span>
            </div>
            <button className="secondary" onClick={handleLogout} style={{ fontSize: '0.85rem', padding: '8px 16px', background: '#fee2e2', color: '#b91c1c', border: '1px solid #fecaca' }}>
              Sign Out 🚪
            </button>
          </div>
        </div>

        {/* Two Column Layout */}
        <div className="unified-workspace-container">
          
          {/* Left Column: Chat Console */}
          <div className="workspace-column">
            <section className="chat-panel">
              <div className="chat-panel-header">
                <h3 style={{ fontSize: '1.1rem' }}>Conversational Agent</h3>
                {!isLocked && (
                  <button 
                    className="secondary" 
                    onClick={handleClearConversation}
                    style={{ fontSize: '0.8rem', padding: '6px 12px' }}
                  >
                    🗑️ Reset Chat
                  </button>
                )}
              </div>
              
              {/* Lock Warning Banners */}
              {isApproved && (
                <div style={{ background: '#ecfdf5', borderBottom: '1px solid #d1fae5', color: '#065f46', padding: '12px 24px', fontSize: '0.85rem' }}>
                  ✅ This project has been <strong>APPROVED</strong> by the Review Committee. The workspace state is now archived and locked.
                </div>
              )}
              {isInReview && (
                <div style={{ background: '#fffbeb', borderBottom: '1px solid #fef3c7', color: '#92400e', padding: '12px 24px', fontSize: '0.85rem' }}>
                  ⏳ This project is currently <strong>UNDER REVIEW</strong>. Editing and chat features are temporarily locked.
                </div>
              )}

              {/* Message Feed */}
              <div className="chat-messages-container" ref={messageListRef}>
                {chatMessages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`message-bubble ${message.role}`}>
                    <div className="message-bubble-header">
                      <span>{message.role === 'ai' ? 'Discovery AI' : currentUser?.name || 'User'}</span>
                    </div>
                    <div>{parseContent(message.text)}</div>
                  </div>
                ))}
              </div>

              {/* Composer Input Area */}
              <div className="chat-composer-section">
                {!isLocked ? (
                  <>
                    <div className="suggestions-chips">
                      <span style={{ fontSize: '0.8rem', fontWeight: '700', color: 'var(--text-muted)', marginRight: '4px' }}>Suggestions:</span>
                      {['Existing software?', 'Number of users?', 'Reporting needs?', 'Integrations?'].map((item) => (
                        <button key={item} className="suggestion-chip" onClick={() => setDraftInput(item)}>
                          {item}
                        </button>
                      ))}
                    </div>

                    <form className="composer-form" onSubmit={handleSend}>
                      <input
                        value={draftInput}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => setDraftInput(event.target.value)}
                        placeholder="Type your response to the discovery agent..."
                        disabled={isLoading}
                      />
                      <button className="primary" type="submit" disabled={isLoading || !draftInput.trim()}>
                        {isLoading ? 'Processing…' : 'Send'}
                      </button>
                    </form>
                  </>
                ) : (
                  <div style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    padding: '14px',
                    borderRadius: '12px',
                    color: 'var(--text-muted)',
                    textAlign: 'center',
                    fontSize: '0.9rem',
                    fontWeight: '500'
                  }}>
                    🔒 {isViewer ? 'You have READ-ONLY permissions.' : 'Chat is locked while project is under review.'}
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* Right Column: Project Control Center Editor */}
          <div className="workspace-column">
            <section className="editor-panel">
              {/* Tab Selector */}
              <div className="editor-tabs-bar">
                <button 
                  className={`editor-tab-button ${activeWorkspaceTab === 'details' ? 'active' : ''}`}
                  onClick={() => setActiveWorkspaceTab('details')}
                >
                  Project Details
                </button>
                <button 
                  className={`editor-tab-button ${activeWorkspaceTab === 'discovery' ? 'active' : ''}`}
                  onClick={() => setActiveWorkspaceTab('discovery')}
                >
                  Discovery
                </button>
                <button 
                  className={`editor-tab-button ${activeWorkspaceTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveWorkspaceTab('overview')}
                >
                  Overview &amp; Scope
                </button>
                <button 
                  className={`editor-tab-button ${activeWorkspaceTab === 'requirements' ? 'active' : ''}`}
                  onClick={() => setActiveWorkspaceTab('requirements')}
                >
                  Requirements ({projectData.functional_requirements?.length || 0})
                </button>
                <button 
                  className={`editor-tab-button ${activeWorkspaceTab === 'members' ? 'active' : ''}`}
                  onClick={() => setActiveWorkspaceTab('members')}
                >
                  Team
                </button>
              </div>

              {/* Tab Contents */}
              <div className="editor-content-area">
                
                {/* 1. Details Tab */}
                {activeWorkspaceTab === 'details' && (
                  <div className="editor-section-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h3>Core Project Details</h3>
                      <span className="sync-status-indicator" style={{ color: 'var(--success)' }}>🟢 Live-Syncing</span>
                    </div>
                    
                    <label>
                      Project Name
                      <input 
                        value={projectData.project?.name || ''} 
                        onChange={(e) => updateField('project', 'name', e.target.value)}
                        placeholder="e.g. ERP Gateway Integration"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Department
                      <input 
                        value={projectData.project?.department || ''} 
                        onChange={(e) => updateField('project', 'department', e.target.value)}
                        placeholder="e.g. Global Logistics"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Business Unit / Industry Domain
                      <input 
                        value={projectData.project?.business_unit || ''} 
                        onChange={(e) => updateField('project', 'business_unit', e.target.value)}
                        placeholder="e.g. Manufacturing / Supply Chain"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Project Sponsor
                      <input 
                        value={projectData.project?.sponsor || ''} 
                        onChange={(e) => updateField('project', 'sponsor', e.target.value)}
                        placeholder="e.g. VP of Operations"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Expected Completion Date (Timeline)
                      <input 
                        value={projectData.project?.expected_completion || ''} 
                        onChange={(e) => updateField('project', 'expected_completion', e.target.value)}
                        placeholder="e.g. Q4 2026 or YYYY-MM-DD"
                        disabled={isLocked}
                      />
                    </label>
                  </div>
                )}

                {/* 2. Discovery Tab */}
                {activeWorkspaceTab === 'discovery' && (
                  <div className="editor-section-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h3>Requirement Discovery Context</h3>
                      <span className="sync-status-indicator" style={{ color: 'var(--success)' }}>🟢 Live-Syncing</span>
                    </div>

                    <label>
                      Business Problem Statement
                      <textarea 
                        value={projectData.discovery?.business_problem || ''} 
                        onChange={(e) => updateField('discovery', 'business_problem', e.target.value)}
                        placeholder="Describe the issue or pain points this project solves..."
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Business Goals
                      <textarea 
                        value={projectData.discovery?.business_goals || ''} 
                        onChange={(e) => updateField('discovery', 'business_goals', e.target.value)}
                        placeholder="What are the strategic business goals of this effort?"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Desired Outcomes
                      <textarea 
                        value={projectData.discovery?.desired_outcomes || ''} 
                        onChange={(e) => updateField('discovery', 'desired_outcomes', e.target.value)}
                        placeholder="What tangible, measurable outcomes are expected?"
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Project Budget &amp; Resource Availability
                      <input 
                        value={projectData.discovery?.budget || ''} 
                        onChange={(e) => updateField('discovery', 'budget', e.target.value)}
                        placeholder="e.g. $150K / 4 Dedicated Software Engineers"
                        disabled={isLocked}
                      />
                    </label>
                  </div>
                )}

                {/* 3. Scope & Constraints Tab */}
                {activeWorkspaceTab === 'overview' && (
                  <div className="editor-section-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h3>System Scope &amp; Constraints</h3>
                      <span className="sync-status-indicator" style={{ color: 'var(--success)' }}>🟢 Live-Syncing</span>
                    </div>

                    <label>
                      General Project Overview Description
                      <textarea 
                        value={projectData.overview?.description || ''} 
                        onChange={(e) => updateField('overview', 'description', e.target.value)}
                        placeholder="Summarize the core scope and system definition..."
                        disabled={isLocked}
                      />
                    </label>

                    <label>
                      Key Stakeholders (Comma separated)
                      <textarea 
                        value={projectData.overview?.stakeholders?.join(', ') || ''} 
                        onChange={(e) => updateField('overview', 'stakeholders', e.target.value.split(',').map(s => s.trim()))}
                        placeholder="e.g. Product Manager, Technical Lead, Security Auditor"
                        disabled={isLocked}
                        style={{ minHeight: '60px' }}
                      />
                    </label>

                    <label>
                      System Integrations (Comma separated)
                      <textarea 
                        value={projectData.discovery?.integrations?.join(', ') || ''} 
                        onChange={(e) => updateField('discovery', 'integrations', e.target.value.split(',').map(s => s.trim()))}
                        placeholder="e.g. ActiveDirectory SSO, Stripe Gateway, Salesforce API"
                        disabled={isLocked}
                        style={{ minHeight: '60px' }}
                      />
                    </label>

                    <label>
                      Constraints &amp; Non-Functional Requirements
                      <textarea 
                        value={projectData.discovery?.constraints || ''} 
                        onChange={(e) => updateField('discovery', 'constraints', e.target.value)}
                        placeholder="Describe constraints like security policies, regulations, latency..."
                        disabled={isLocked}
                      />
                    </label>
                  </div>
                )}

                {/* 4. Functional Requirements Tab */}
                {activeWorkspaceTab === 'requirements' && (
                  <div className="requirements-tab-layout">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h3>Functional Requirements Cards</h3>
                      {!isLocked && (
                        <button className="primary" onClick={handleAddRequirement} style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
                          ➕ Add Card
                        </button>
                      )}
                    </div>

                    <div className="requirement-list-container">
                      {projectData.functional_requirements && projectData.functional_requirements.length > 0 ? (
                        projectData.functional_requirements.map((item, index) => (
                          <div key={index} className="requirement-editor-row">
                            <input 
                              value={item.title || ''} 
                              onChange={(e) => handleUpdateRequirement(index, 'title', e.target.value)}
                              placeholder="Requirement description..."
                              disabled={isLocked}
                              style={{ border: 'none', background: 'transparent', padding: '4px' }}
                            />
                            
                            <select 
                              value={item.priority || 'Medium'} 
                              onChange={(e) => handleUpdateRequirement(index, 'priority', e.target.value)}
                              disabled={isLocked}
                              style={{ padding: '4px 8px', borderRadius: '6px' }}
                            >
                              <option value="High">🔴 High</option>
                              <option value="Medium">🟡 Medium</option>
                              <option value="Low">🟢 Low</option>
                            </select>

                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                              Confidence: <strong>{(item.confidence * 100).toFixed(0)}%</strong>
                            </div>

                            {!isLocked && (
                              <button 
                                className="requirement-delete-btn" 
                                onClick={() => handleDeleteRequirement(index)}
                                title="Delete Requirement"
                              >
                                🗑️
                              </button>
                            )}
                          </div>
                        ))
                      ) : (
                        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
                          No functional requirements captured yet. Use the chat agent to discover requirements or click Add Card.
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* 5. Team Tab */}
                {activeWorkspaceTab === 'members' && (
                  <div className="editor-section-card">
                    <h3>Project Collaboration</h3>
                    
                    {isOwnerOrAdmin && !isLocked ? (
                      <form onSubmit={handleInviteMember} style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid #e2e8f0' }}>
                        <label style={{ gap: '4px' }}>
                          Invite User by Email
                          <input 
                            type="email" 
                            value={inviteEmail} 
                            onChange={e => setInviteEmail(e.target.value)}
                            placeholder="colleague@company.com"
                            required
                          />
                        </label>
                        
                        <label style={{ gap: '4px' }}>
                          Project Role
                          <select 
                            value={inviteRole} 
                            onChange={e => setInviteRole(e.target.value as ProjectMemberRole)}
                            style={{ background: 'white' }}
                          >
                            <option value="EDITOR">Editor (Can Chat &amp; Edit)</option>
                            <option value="VIEWER">Viewer (Read Only)</option>
                          </select>
                        </label>

                        <button type="submit" className="primary" style={{ padding: '8px', fontSize: '0.85rem' }}>
                          Invite Member
                        </button>
                      </form>
                    ) : null}

                    <div>
                      <h4 style={{ margin: '0 0 10px 0', fontSize: '0.9rem', color: 'var(--text-muted)' }}>Project Members List</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {/* Show Owner first */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc', padding: '8px 12px', borderRadius: '8px' }}>
                          <div>
                            <div style={{ fontSize: '0.85rem', fontWeight: '700', color: '#1e293b' }}>
                              {isOwnerOrAdmin && projectData.owner_id === currentUser?.id ? 'You' : 'Project Owner'}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Creator</div>
                          </div>
                          <span className="badge">OWNER</span>
                        </div>

                        {projectMembers.filter(m => m.role !== 'OWNER').map(m => (
                          <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc', padding: '8px 12px', borderRadius: '8px' }}>
                            <div style={{ maxWidth: '180px', overflow: 'hidden' }}>
                              <div style={{ fontSize: '0.85rem', fontWeight: '700', color: '#1e293b', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{m.name}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{m.email}</div>
                            </div>
                            <span style={{ 
                              fontSize: '0.7rem', 
                              padding: '2px 6px', 
                              background: m.role === 'EDITOR' ? '#f0fdf4' : '#f1f5f9', 
                              color: m.role === 'EDITOR' ? '#166534' : '#475569', 
                              borderRadius: '6px', 
                              fontWeight: '700' 
                            }}>
                              {m.role}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>

        {notice && (
          <div className="toast">
            <strong>{notice.title}</strong>
            <p>{notice.detail}</p>
          </div>
        )}
      </div>
    )
  }

  const renderReview = () => {
    const isReviewerOrAdmin = currentUser && (currentUser.role === 'REVIEWER' || currentUser.role === 'ADMIN')
    const isApproved = projectData.status === 'APPROVED'
    
    return (
      <div className="review-workspace-layout">
        <div style={{ gridColumn: 'span 2', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid #e7ebf2' }}>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <button 
              className="secondary" 
              onClick={() => setActivePage('interview')}
              style={{ padding: '8px 14px', fontSize: '0.9rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              ⬅ Back to Chat
            </button>
            <div>
              <p className="eyebrow">Review Workspace</p>
              <h2>Compile &amp; Export Requirements</h2>
            </div>
          </div>
          <button className="primary" onClick={() => setActivePage('interview')}>
            Back to Chat Workspace
          </button>
        </div>

        {/* Status specific notices */}
        {projectData.status === 'IN_REVIEW' && (
          <div style={{ gridColumn: 'span 2', background: '#fffbeb', border: '1px solid #fef3c7', color: '#92400e', padding: '16px', borderRadius: '12px', marginBottom: '20px' }}>
            <strong>⏳ Project Review Pending:</strong> This project requirements checklist has been submitted for review.
          </div>
        )}
        {projectData.status === 'APPROVED' && (
          <div style={{ gridColumn: 'span 2', background: '#ecfdf5', border: '1px solid #d1fae5', color: '#065f46', padding: '16px', borderRadius: '12px', marginBottom: '20px' }}>
            <strong>✅ Approved requirements:</strong> This requirements documentation is fully approved.
          </div>
        )}

        <div className="review-main-column">
          <section className="page review-card">
            <div className="section-heading">
              <h2>Requirement Discovery Checklist</h2>
              <span className="badge success">{completion}%</span>
            </div>

            <div className="review-actions" style={{ marginTop: '20px' }}>
              {projectRole === 'OWNER' && projectData.status === 'DRAFT' && (
                <>
                  <button className="secondary" onClick={() => handleReviewAction('Edit Overview')}>
                    Edit Overview
                  </button>
                  <button className="secondary" onClick={() => handleReviewAction('Edit Discovery')}>
                    Edit Discovery
                  </button>
                  <button className="secondary" onClick={() => handleReviewAction('Edit Functional Requirements')}>
                    Edit Functional Requirements
                  </button>
                </>
              )}

              <button className="primary" onClick={() => handleReviewAction('Generate DOCX')} disabled={isLoading}>
                Generate DOCX
              </button>
              <button className="secondary" onClick={() => handleReviewAction('Generate PDF')} disabled={isLoading}>
                Generate PDF
              </button>
            </div>

            {/* Reviewer decision panel */}
            {isReviewerOrAdmin && projectData.status === 'IN_REVIEW' && (
              <div style={{
                background: '#f8fafc',
                border: '1px solid #cbd5e1',
                padding: '24px',
                borderRadius: '16px',
                marginTop: '24px',
                display: 'flex',
                flexDirection: 'column',
                gap: '14px'
              }}>
                <h3 style={{ margin: '0', color: '#0f172a' }}>Review Decision Portal</h3>
                <p style={{ margin: '0', color: '#475569', fontSize: '0.9rem' }}>
                  Please inspect the discovery details and requirements cards on the right column before approving or rejecting.
                </p>
                <textarea
                  value={reviewerFeedback}
                  onChange={e => setReviewerFeedback(e.target.value)}
                  placeholder="Provide review notes or rejection feedback..."
                  rows={3}
                  style={{
                    padding: '10px 14px',
                    borderRadius: '10px',
                    border: '1px solid #cbd5e1',
                    fontSize: '0.9rem',
                    width: '100%',
                    fontFamily: 'inherit'
                  }}
                />
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button className="primary" style={{ backgroundColor: '#10b981' }} onClick={() => handleReviewProject(true)}>
                    Approve FDR Document
                  </button>
                  <button className="secondary" style={{ backgroundColor: '#ef4444', color: 'white' }} onClick={() => handleReviewProject(false)}>
                    Reject &amp; Return Draft
                  </button>
                </div>
              </div>
            )}

            <div className="preview-card" style={{ marginTop: '32px' }}>
              <div className="preview-heading" style={{ marginBottom: '16px' }}>
                <h3>Formal Discovery Document Preview</h3>
                <span className="badge success">Ready for Review</span>
              </div>
              
              <div className="document-sheet-preview-container">
                {/* Page 1: Title & Core Context */}
                <div className="document-sheet-page">
                  <div className="document-header-deco">
                    <h3>PROJECT REQUIREMENTS INTAKE DOCUMENT</h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: '2px' }}>
                      Final Discovery Report (FDR) - Generated by AI Discovery Agent
                    </p>
                  </div>

                  <section>
                    <h4 style={{ color: 'var(--primary)', marginBottom: '14px', fontSize: '1.05rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '4px' }}>
                      1. Core Project Metadata
                    </h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div className="document-field-block">
                        <strong>Project Name</strong>
                        <p>{projectData.project?.name || <em style={{ color: '#aaa' }}>Unspecified</em>}</p>
                      </div>
                      <div className="document-field-block">
                        <strong>Department / Business Unit</strong>
                        <p>
                          {projectData.project?.department || 'Unspecified'} 
                          {projectData.project?.business_unit ? ` (${projectData.project.business_unit})` : ''}
                        </p>
                      </div>
                      <div className="document-field-block">
                        <strong>Project Sponsor</strong>
                        <p>{projectData.project?.sponsor || <em style={{ color: '#aaa' }}>Unspecified</em>}</p>
                      </div>
                      <div className="document-field-block">
                        <strong>Timeline &amp; Expected Completion</strong>
                        <p>{projectData.project?.expected_completion || <em style={{ color: '#aaa' }}>Unspecified</em>}</p>
                      </div>
                      <div className="document-field-block" style={{ gridColumn: 'span 2' }}>
                        <strong>Estimated Budget &amp; Resource allocation</strong>
                        <p>{projectData.discovery?.budget || <em style={{ color: '#aaa' }}>Unspecified</em>}</p>
                      </div>
                    </div>
                  </section>

                  <section style={{ marginTop: '24px' }}>
                    <h4 style={{ color: 'var(--primary)', marginBottom: '14px', fontSize: '1.05rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '4px' }}>
                      2. Project Context &amp; Objectives
                    </h4>
                    <div className="document-field-block">
                      <strong>Executive Summary &amp; Overview</strong>
                      <p>{projectData.overview?.description || <em style={{ color: '#aaa' }}>Not captured yet</em>}</p>
                    </div>
                    <div className="document-field-block">
                      <strong>Target Stakeholders</strong>
                      <p>{projectData.overview?.stakeholders?.join(', ') || <em style={{ color: '#aaa' }}>Not captured yet</em>}</p>
                    </div>
                    <div className="document-field-block">
                      <strong>Business Problem Statement</strong>
                      <p>{projectData.discovery?.business_problem || <em style={{ color: '#aaa' }}>Not captured yet</em>}</p>
                    </div>
                    <div className="document-field-block">
                      <strong>Strategic Business Goals</strong>
                      <p>{projectData.discovery?.business_goals || <em style={{ color: '#aaa' }}>Not captured yet</em>}</p>
                    </div>
                  </section>
                </div>

                {/* Page 2: Scope & Functional Requirements */}
                <div className="document-sheet-page">
                  <div className="document-header-deco">
                    <h3>SYSTEM SCOPE &amp; SPECIFICATIONS</h3>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: '2px' }}>
                      FDR Specifications Section
                    </p>
                  </div>

                  <section>
                    <h4 style={{ color: 'var(--primary)', marginBottom: '14px', fontSize: '1.05rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '4px' }}>
                      3. Technical Integration &amp; NFRs
                    </h4>
                    <div className="document-field-block">
                      <strong>Third-Party Integrations</strong>
                      <p>{projectData.discovery?.integrations?.join(', ') || <em style={{ color: '#aaa' }}>None specified</em>}</p>
                    </div>
                    <div className="document-field-block">
                      <strong>Constraints &amp; Non-Functional Requirements</strong>
                      <p>{projectData.discovery?.constraints || <em style={{ color: '#aaa' }}>None specified</em>}</p>
                    </div>
                  </section>

                  <section style={{ marginTop: '24px' }}>
                    <h4 style={{ color: 'var(--primary)', marginBottom: '14px', fontSize: '1.05rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '4px' }}>
                      4. Scope &amp; Functional Requirements Checklist
                    </h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {projectData.functional_requirements && projectData.functional_requirements.length > 0 ? (
                        projectData.functional_requirements.map((item, index) => (
                          <div key={index} style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '6px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                              <strong>FDR-REQ-{String(index + 1).padStart(3, '0')}: {item.title}</strong>
                              <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: item.priority === 'High' ? 'var(--danger)' : 'var(--text-muted)' }}>
                                Priority: {item.priority}
                              </span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p style={{ fontStyle: 'italic', color: '#aaa' }}>No functional requirements captured in workspace yet.</p>
                      )}
                    </div>
                  </section>
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
        </div>
      </div>
    )
  }

  const renderExport = () => {
    return (
      <div className="page centered-page" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '16px' }}>
        <button 
          className="secondary" 
          onClick={() => setActivePage('interview')}
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', fontSize: '0.9rem' }}
        >
          ⬅ Back to Chat
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
  }

  const renderAdmin = () => {
    return (
      <div className="admin-layout" style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #e2e8f0', paddingBottom: '16px' }}>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <button 
              className="secondary" 
              onClick={() => setActivePage('interview')}
              style={{ padding: '8px 14px', fontSize: '0.9rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0' }}
            >
              🧑‍💼 Switch to BA Mode
            </button>
            <div>
              <p className="eyebrow" style={{ margin: '0' }}>Administration</p>
              <h2 style={{ margin: '4px 0 0 0' }}>System Control Panel</h2>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button 
              className={adminTab === 'users' ? 'primary' : 'secondary'} 
              onClick={() => setAdminTab('users')}
              style={{ cursor: 'pointer' }}
            >
              👤 Users Management
            </button>
            <button 
              className={adminTab === 'logs' ? 'primary' : 'secondary'} 
              onClick={() => setAdminTab('logs')}
              style={{ cursor: 'pointer' }}
            >
              📜 Audit Logs
            </button>
          </div>
        </div>

        {adminTab === 'users' ? (
          <div style={{ display: 'grid', gridTemplateColumns: '3fr 1.5fr', gap: '24px' }}>
            {/* Users List */}
            <section className="panel" style={{ padding: '24px' }}>
              <h3>Users under Administration</h3>
              <div style={{ overflowX: 'auto', marginTop: '16px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e2e8f0', color: '#475569', fontSize: '0.9rem' }}>
                      <th style={{ padding: '12px' }}>ID</th>
                      <th style={{ padding: '12px' }}>Name</th>
                      <th style={{ padding: '12px' }}>Email</th>
                      <th style={{ padding: '12px' }}>Role</th>
                      <th style={{ padding: '12px' }}>Joined</th>
                      <th style={{ padding: '12px' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersList.map((u) => (
                      <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9', fontSize: '0.9rem' }}>
                        <td style={{ padding: '12px', fontWeight: 'bold' }}>{u.id}</td>
                        <td style={{ padding: '12px' }}>{u.name}</td>
                        <td style={{ padding: '12px', color: '#475569' }}>{u.email}</td>
                        <td style={{ padding: '12px' }}>
                          <span style={{
                            background: u.role === 'ADMIN' ? '#fee2e2' : u.role === 'BUSINESS_ANALYST' ? '#dbeafe' : u.role === 'REVIEWER' ? '#fef3c7' : '#f1f5f9',
                            color: u.role === 'ADMIN' ? '#991b1b' : u.role === 'BUSINESS_ANALYST' ? '#1e40af' : u.role === 'REVIEWER' ? '#92400e' : '#475569',
                            padding: '4px 8px',
                            borderRadius: '6px',
                            fontSize: '0.75rem',
                            fontWeight: '700'
                          }}>
                            {u.role}
                          </span>
                        </td>
                        <td style={{ padding: '12px', color: '#64748b' }}>
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : 'N/A'}
                        </td>
                        <td style={{ padding: '12px' }}>
                          {u.id === currentUser?.id ? (
                            <span style={{ fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic' }}>Active Admin (Self)</span>
                          ) : (
                            <select 
                              value={u.role} 
                              onChange={(e) => handleUpdateUserRole(u.id, e.target.value)}
                              style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.85rem', cursor: 'pointer' }}
                            >
                              <option value="ADMIN">ADMIN</option>
                              <option value="BUSINESS_ANALYST">BUSINESS_ANALYST</option>
                              <option value="REVIEWER">REVIEWER</option>
                              <option value="CLIENT">CLIENT</option>
                            </select>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Add User Form */}
            <section className="panel" style={{ padding: '24px', height: 'fit-content' }}>
              <h3 style={{ marginBottom: '16px' }}>Add User</h3>
              <form onSubmit={handleCreateUserByAdmin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.9rem', fontWeight: '600' }}>
                  Full Name
                  <input 
                    type="text" 
                    value={adminNewName}
                    onChange={(e) => setAdminNewName(e.target.value)}
                    placeholder="Enter full name"
                    required
                    style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.9rem', fontWeight: '600' }}>
                  Email Address
                  <input 
                    type="email" 
                    value={adminNewEmail}
                    onChange={(e) => setAdminNewEmail(e.target.value)}
                    placeholder="name@example.com"
                    required
                    style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.9rem', fontWeight: '600' }}>
                  Password
                  <input 
                    type="password" 
                    value={adminNewPassword}
                    onChange={(e) => setAdminNewPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.9rem', fontWeight: '600' }}>
                  System Role
                  <select
                    value={adminNewRole}
                    onChange={(e) => setAdminNewRole(e.target.value as UserRole)}
                    style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', cursor: 'pointer' }}
                  >
                    <option value="BUSINESS_ANALYST">BUSINESS_ANALYST</option>
                    <option value="ADMIN">ADMIN</option>
                    <option value="REVIEWER">REVIEWER</option>
                    <option value="CLIENT">CLIENT</option>
                  </select>
                </label>
                <button type="submit" className="primary" style={{ marginTop: '10px', width: '100%' }}>
                  Create Account ➕
                </button>
              </form>
            </section>
          </div>
        ) : (
          <section className="panel" style={{ padding: '24px' }}>
            <h3>System Audit Feed</h3>
            <div style={{ overflowX: 'auto', marginTop: '16px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', color: '#475569', fontSize: '0.9rem' }}>
                    <th style={{ padding: '12px' }}>Timestamp</th>
                    <th style={{ padding: '12px' }}>User Email</th>
                    <th style={{ padding: '12px' }}>Action</th>
                    <th style={{ padding: '12px' }}>Project ID</th>
                    <th style={{ padding: '12px' }}>Metadata / Details</th>
                  </tr>
                </thead>
                <tbody>
                  {logsList.map((l) => (
                    <tr key={l.id} style={{ borderBottom: '1px solid #f1f5f9', fontSize: '0.85rem' }}>
                      <td style={{ padding: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                        {new Date(l.timestamp).toLocaleString()}
                      </td>
                      <td style={{ padding: '12px', fontWeight: '600' }}>{l.user_email}</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{
                          background: l.action === 'permission denied' ? '#fee2e2' : '#e2e8f0',
                          color: l.action === 'permission denied' ? '#ef4444' : '#1e293b',
                          padding: '4px 8px',
                          borderRadius: '6px',
                          fontWeight: '600',
                          fontSize: '0.75rem'
                        }}>
                          {l.action}
                        </span>
                      </td>
                      <td style={{ padding: '12px', color: '#475569' }}>{l.project_id || 'N/A'}</td>
                      <td style={{ padding: '12px', fontFamily: 'monospace', color: '#475569', fontSize: '0.75rem', maxWidth: '350px', wordBreak: 'break-all' }}>
                        {l.metadata ? JSON.stringify(l.metadata) : 'None'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    )
  }

  // If not authenticated, render Login/Register
  if (!token || !currentUser) {
    if (isLoaded) {
      return renderAuthPage()
    } else {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#f4f7fb' }}>
          <div style={{ fontSize: '1.2rem', color: '#3755d4', fontWeight: 'bold' }}>Loading Workshop Console...</div>
        </div>
      )
    }
  }

  if (activePage === 'admin' && currentUser && (currentUser.role === 'SUPER_ADMIN' || currentUser.role === 'ADMIN')) {
    return (
      <AdminPortal 
        token={token!} 
        currentUser={currentUser} 
        onLogout={handleLogout} 
        onSwitchMode={() => {
          setActivePage('dashboard')
          window.history.pushState({}, '', '/')
        }}
        projectsCount={projectsList.length}
      />
    )
  }

  return (
    <div className="app-shell">
      {activePage !== 'interview' && (
        <header className="header" style={{ borderBottom: '1px solid #dce5f0' }}>
          <div>
            <p className="eyebrow" style={{ margin: '0' }}>BA Agent Workspace</p>
            <h2 style={{ margin: '4px 0 0 0' }}>Business Analyst Workshop</h2>
          </div>
          <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
            {(currentUser?.role === 'SUPER_ADMIN' || currentUser?.role === 'ADMIN') && (
              <button 
                className="secondary" 
                onClick={() => {
                  setActivePage('admin')
                  window.history.pushState({}, '', '/admin')
                }} 
                style={{ fontSize: '0.85rem', padding: '8px 16px', background: '#eff6ff', color: '#1e40af', border: '1px solid #bfdbfe', cursor: 'pointer' }}
              >
                🛡️ Admin Panel
              </button>
            )}
            <div className="profile-pill" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', borderRadius: '12px', background: '#f8fafc', border: '1px solid #cbd5e1', padding: '6px 14px' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: '700', color: '#1e293b' }}>{currentUser?.name}</span>
              <span style={{ fontSize: '0.7rem', fontWeight: '700', color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {currentUser && getRoleLabel(currentUser.role)}
              </span>
            </div>
            <button className="secondary" onClick={handleLogout} style={{ fontSize: '0.85rem', padding: '8px 16px', background: '#fee2e2', color: '#b91c1c', border: '1px solid #fecaca', cursor: 'pointer' }}>
              Sign Out 🚪
            </button>
          </div>
        </header>
      )}

      <div className="workspace">
        <main className="main-content">
          {activePage === 'dashboard' && renderDashboard()}
          {activePage === 'interview' && renderInterview()}
          {activePage === 'review' && renderReview()}
          {activePage === 'export' && renderExport()}
        </main>
      </div>
    </div>
  )
}

export default App
