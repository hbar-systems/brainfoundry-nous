import { useEffect, useState } from 'react'

export default function Chat() {
    const [models, setModels] = useState([])
    const [selectedModel, setSelectedModel] = useState('')
    const [messages, setMessages] = useState([])
    const [inputMessage, setInputMessage] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)

    // Chat session management
    const [sessions, setSessions] = useState([])
    const [currentSessionId, setCurrentSessionId] = useState(null)
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [isCreatingSession, setIsCreatingSession] = useState(false)

    // Modal state for naming new chats
    const [showNameModal, setShowNameModal] = useState(false)
    const [newChatName, setNewChatName] = useState('')

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

    // Fetch available models on component mount
    useEffect(() => {
        const fetchModels = async () => {
            try {
                const response = await fetch(`${API_URL}/models`)
                if (response.ok) {
                    const data = await response.json()
                    setModels(data.models || [])
                    if (data.models && data.models.length > 0) {
                        setSelectedModel(data.models[0].name)
                    }
                } else {
                    setError('Failed to fetch models')
                }
            } catch (err) {
                setError(`Connection error: ${err.message}`)
            }
        }

        fetchModels()
    }, [API_URL])

    // Fetch chat sessions
    const fetchSessions = async () => {
        try {
            const response = await fetch(`${API_URL}/sessions`)
            if (response.ok) {
                const data = await response.json()
                setSessions(data.sessions || [])
            }
        } catch (err) {
            console.error('Failed to fetch sessions:', err)
        }
    }

    useEffect(() => {
        fetchSessions()
    }, [API_URL])

    // Load messages for a specific session
    const loadSessionMessages = async (sessionId) => {
        try {
            const response = await fetch(`${API_URL}/sessions/${sessionId}/messages`)
            if (response.ok) {
                const data = await response.json()
                setMessages(data.messages || [])
                setCurrentSessionId(sessionId)
            }
        } catch (err) {
            console.error('Failed to load session messages:', err)
        }
    }

    // Create new chat session
    const createNewSession = async (customTitle = 'New Chat') => {
        if (!selectedModel) {
            setError('Please select a model first')
            return
        }

        setIsCreatingSession(true)
        try {
            const response = await fetch(`${API_URL}/sessions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_name: selectedModel,
                    title: customTitle
                })
            })

            if (response.ok) {
                const newSession = await response.json()
                setCurrentSessionId(newSession.session_id)
                setMessages([])
                fetchSessions() // Refresh sessions list
            }
        } catch (err) {
            setError('Failed to create new session')
        } finally {
            setIsCreatingSession(false)
        }
    }

    // Open modal for naming new chat
    const openNewChatModal = () => {
        if (!selectedModel) {
            setError('Please select a model first')
            return
        }
        setNewChatName('')
        setShowNameModal(true)
    }

    // Close modal
    const closeNewChatModal = () => {
        setShowNameModal(false)
        setNewChatName('')
    }

    // Handle modal form submission
    const handleCreateNamedChat = async (e) => {
        e.preventDefault()
        const chatName = newChatName.trim() || 'New Chat'
        closeNewChatModal()
        await createNewSession(chatName)
    }

    // Delete a chat session
    const deleteSession = async (sessionId) => {
        try {
            const response = await fetch(`${API_URL}/sessions/${sessionId}`, {
                method: 'DELETE'
            })

            if (response.ok) {
                if (currentSessionId === sessionId) {
                    setCurrentSessionId(null)
                    setMessages([])
                }
                fetchSessions() // Refresh sessions list
            }
        } catch (err) {
            setError('Failed to delete session')
        }
    }

    const sendMessage = async () => {
        if (!inputMessage.trim() || !selectedModel || isLoading) return

        // Create new session if none exists
        if (!currentSessionId) {
            await createNewSession()
            // Wait a moment for session to be created
            await new Promise(resolve => setTimeout(resolve, 500))
        }

        const userMessage = { role: 'user', content: inputMessage.trim() }
        const updatedMessages = [...messages, userMessage]
        setMessages(updatedMessages)
        setInputMessage('')
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch(`${API_URL}/chat/completions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: selectedModel,
                    messages: updatedMessages,
                    session_id: currentSessionId,
                    max_tokens: 500
                })
            })

            if (response.ok) {
                const data = await response.json()
                const assistantMessage = {
                    role: 'assistant',
                    content: data.choices[0].message.content
                }
                setMessages([...updatedMessages, assistantMessage])

                // Refresh sessions to update message counts
                fetchSessions()
            } else {
                const errorData = await response.json()
                setError(`API Error: ${errorData.detail || 'Unknown error'}`)
            }
        } catch (err) {
            setError(`Network error: ${err.message}`)
        } finally {
            setIsLoading(false)
        }
    }

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            sendMessage()
        }
    }

    const formatDate = (dateString) => {
        if (!dateString) return 'Unknown'
        const date = new Date(dateString)
        const now = new Date()
        const diffTime = now - date
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))

        if (diffDays === 0) return 'Today'
        if (diffDays === 1) return 'Yesterday'
        if (diffDays < 7) return `${diffDays} days ago`
        return date.toLocaleDateString()
    }

    return (
        <div style={{
            minHeight: '100vh',
            backgroundColor: '#0a0a0a',
            color: '#e5e5e5',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            display: 'flex',
            margin: 0,
            padding: 0,
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            width: '100vw'
        }}>
            {/* Sidebar */}
            <div style={{
                width: sidebarOpen ? '320px' : '0',
                backgroundColor: '#1a1a1a',
                borderRight: '1px solid #333',
                display: 'flex',
                flexDirection: 'column',
                transition: 'width 0.3s ease',
                overflow: 'hidden'
            }}>
                {/* Sidebar Header */}
                <div style={{
                    padding: '20px',
                    borderBottom: '1px solid #333',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                }}>
                    <div style={{
                        fontSize: '1.2rem',
                        fontWeight: '600',
                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent'
                    }}>
                        💬 Chat History
                    </div>
                    <button
                        onClick={openNewChatModal}
                        disabled={isCreatingSession || !selectedModel}
                        style={{
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            padding: '8px 12px',
                            fontSize: '14px',
                            cursor: isCreatingSession || !selectedModel ? 'not-allowed' : 'pointer',
                            opacity: isCreatingSession || !selectedModel ? 0.5 : 1
                        }}
                    >
                        {isCreatingSession ? '...' : '+ New'}
                    </button>
                </div>

                {/* Sessions List */}
                <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '10px'
                }}>
                    {sessions.length === 0 ? (
                        <div style={{
                            textAlign: 'center',
                            color: '#666',
                            padding: '40px 20px'
                        }}>
                            <div style={{ fontSize: '2rem', marginBottom: '12px' }}>💭</div>
                            <p>No chats yet</p>
                            <p style={{ fontSize: '14px' }}>Create your first chat!</p>
                        </div>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.session_id}
                                onClick={() => loadSessionMessages(session.session_id)}
                                style={{
                                    padding: '12px 16px',
                                    margin: '4px 0',
                                    borderRadius: '10px',
                                    cursor: 'pointer',
                                    backgroundColor: currentSessionId === session.session_id ? '#667eea20' : 'transparent',
                                    border: currentSessionId === session.session_id ? '1px solid #667eea40' : '1px solid transparent',
                                    transition: 'all 0.2s ease',
                                    position: 'relative',
                                    group: 'session'
                                }}
                                onMouseOver={(e) => {
                                    if (currentSessionId !== session.session_id) {
                                        e.target.style.backgroundColor = '#2a2a2a'
                                    }
                                }}
                                onMouseOut={(e) => {
                                    if (currentSessionId !== session.session_id) {
                                        e.target.style.backgroundColor = 'transparent'
                                    }
                                }}
                            >
                                <div style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'flex-start',
                                    marginBottom: '8px'
                                }}>
                                    <div style={{
                                        fontSize: '14px',
                                        fontWeight: '500',
                                        color: '#e5e5e5',
                                        flex: 1,
                                        marginRight: '8px'
                                    }}>
                                        {session.title || 'New Chat'}
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            deleteSession(session.session_id)
                                        }}
                                        style={{
                                            background: 'none',
                                            border: 'none',
                                            color: '#ff6b6b',
                                            cursor: 'pointer',
                                            padding: '2px 4px',
                                            borderRadius: '4px',
                                            fontSize: '14px',
                                            opacity: 0.7
                                        }}
                                        onMouseOver={(e) => {
                                            e.target.style.opacity = 1
                                            e.target.style.backgroundColor = '#ff6b6b20'
                                        }}
                                        onMouseOut={(e) => {
                                            e.target.style.opacity = 0.7
                                            e.target.style.backgroundColor = 'transparent'
                                        }}
                                    >
                                        ×
                                    </button>
                                </div>

                                <div style={{
                                    fontSize: '12px',
                                    color: '#888',
                                    marginBottom: '4px'
                                }}>
                                    {session.model_name} • {session.message_count} messages
                                </div>

                                {session.last_message && (
                                    <div style={{
                                        fontSize: '12px',
                                        color: '#666',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap'
                                    }}>
                                        {session.last_message}
                                    </div>
                                )}

                                <div style={{
                                    fontSize: '11px',
                                    color: '#555',
                                    marginTop: '6px'
                                }}>
                                    {formatDate(session.created_at)}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Main Chat Area */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                {/* Header */}
                <header style={{
                    backgroundColor: '#1a1a1a',
                    borderBottom: '1px solid #333',
                    padding: '16px 24px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <button
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            style={{
                                background: 'none',
                                border: '1px solid #333',
                                color: '#e5e5e5',
                                padding: '8px 12px',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                fontSize: '14px'
                            }}
                        >
                            {sidebarOpen ? '◀' : '▶'}
                        </button>

                        <a
                            href="/"
                            style={{
                                color: '#667eea',
                                textDecoration: 'none',
                                fontSize: '14px',
                                padding: '8px 16px',
                                borderRadius: '8px',
                                backgroundColor: '#1a1a2e',
                                border: '1px solid #667eea30'
                            }}
                        >
                            ← Home
                        </a>

                        <h1 style={{
                            fontSize: '1.5rem',
                            fontWeight: '700',
                            margin: 0,
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent'
                        }}>
                            🤖 LLM Chat
                        </h1>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <select
                            value={selectedModel}
                            onChange={(e) => setSelectedModel(e.target.value)}
                            style={{
                                padding: '10px 16px',
                                borderRadius: '10px',
                                border: '1px solid #333',
                                backgroundColor: '#2a2a2a',
                                color: '#e5e5e5',
                                fontSize: '14px',
                                minWidth: '220px',
                                cursor: 'pointer',
                                outline: 'none'
                            }}
                        >
                            <option value="">Select Model</option>
                            {models.map((model) => (
                                <option key={model.name} value={model.name}>
                                    {model.name} ({(model.size / 1e9).toFixed(1)}GB)
                                </option>
                            ))}
                        </select>
                    </div>
                </header>

                {/* Messages Area */}
                <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '30px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px'
                }}>
                    {messages.length === 0 && (
                        <div style={{
                            textAlign: 'center',
                            color: '#888',
                            marginTop: '100px'
                        }}>
                            <div style={{
                                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                WebkitBackgroundClip: 'text',
                                WebkitTextFillColor: 'transparent',
                                fontSize: '3rem',
                                marginBottom: '20px'
                            }}>
                                🤖
                            </div>
                            <h3 style={{
                                color: '#e5e5e5',
                                fontSize: '1.8rem',
                                fontWeight: '600',
                                marginBottom: '12px'
                            }}>
                                {currentSessionId ? 'Ready to chat!' : 'Start a new conversation'}
                            </h3>
                            <p style={{
                                color: '#a0a0a0',
                                fontSize: '1.1rem'
                            }}>
                                {currentSessionId ? 'Type a message below to get started' : 'Your first message will create a new chat session'}
                            </p>
                        </div>
                    )}

                    {messages.map((message, index) => (
                        <div
                            key={index}
                            style={{
                                display: 'flex',
                                justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
                                marginBottom: '8px'
                            }}
                        >
                            <div style={{
                                maxWidth: '75%',
                                padding: '16px 20px',
                                borderRadius: '20px',
                                backgroundColor: message.role === 'user'
                                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                                    : '#1a1a1a',
                                background: message.role === 'user'
                                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                                    : '#1a1a1a',
                                color: message.role === 'user' ? 'white' : '#e5e5e5',
                                border: message.role === 'user' ? 'none' : '1px solid #333',
                                boxShadow: message.role === 'user'
                                    ? '0 4px 15px rgba(102, 126, 234, 0.3)'
                                    : '0 4px 15px rgba(0,0,0,0.2)',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                            }}>
                                <div style={{
                                    fontSize: '12px',
                                    opacity: 0.8,
                                    marginBottom: '8px',
                                    fontWeight: '500'
                                }}>
                                    {message.role === 'user' ? 'You' : selectedModel}
                                </div>
                                <div style={{ lineHeight: '1.6' }}>
                                    {message.content}
                                </div>
                            </div>
                        </div>
                    ))}

                    {isLoading && (
                        <div style={{
                            display: 'flex',
                            justifyContent: 'flex-start',
                            marginBottom: '8px'
                        }}>
                            <div style={{
                                maxWidth: '75%',
                                padding: '16px 20px',
                                borderRadius: '20px',
                                backgroundColor: '#1a1a1a',
                                color: '#a0a0a0',
                                border: '1px solid #333',
                                boxShadow: '0 4px 15px rgba(0,0,0,0.2)'
                            }}>
                                <div style={{
                                    fontSize: '12px',
                                    opacity: 0.8,
                                    marginBottom: '8px',
                                    fontWeight: '500'
                                }}>
                                    {selectedModel}
                                </div>
                                <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px'
                                }}>
                                    <div style={{
                                        width: '6px',
                                        height: '6px',
                                        backgroundColor: '#667eea',
                                        borderRadius: '50%',
                                        animation: 'pulse 1.5s infinite'
                                    }}></div>
                                    <div style={{
                                        width: '6px',
                                        height: '6px',
                                        backgroundColor: '#667eea',
                                        borderRadius: '50%',
                                        animation: 'pulse 1.5s infinite',
                                        animationDelay: '0.2s'
                                    }}></div>
                                    <div style={{
                                        width: '6px',
                                        height: '6px',
                                        backgroundColor: '#667eea',
                                        borderRadius: '50%',
                                        animation: 'pulse 1.5s infinite',
                                        animationDelay: '0.4s'
                                    }}></div>
                                    <span style={{ marginLeft: '8px' }}>Thinking...</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div style={{
                            backgroundColor: '#2a1a1a',
                            color: '#ff6b6b',
                            padding: '16px 20px',
                            borderRadius: '12px',
                            border: '1px solid #ff6b6b30',
                            marginBottom: '20px'
                        }}>
                            <strong>Error:</strong> {error}
                        </div>
                    )}
                </div>

                {/* Input Area */}
                <div style={{
                    backgroundColor: '#1a1a1a',
                    borderTop: '1px solid #333',
                    padding: '24px 30px'
                }}>
                    <div style={{
                        display: 'flex',
                        gap: '16px',
                        alignItems: 'flex-end'
                    }}>
                        <textarea
                            value={inputMessage}
                            onChange={(e) => setInputMessage(e.target.value)}
                            onKeyPress={handleKeyPress}
                            placeholder={selectedModel ? "Type your message... (Enter to send, Shift+Enter for new line)" : "Please select a model first"}
                            disabled={!selectedModel || isLoading}
                            style={{
                                flex: 1,
                                minHeight: '50px',
                                maxHeight: '150px',
                                padding: '16px 20px',
                                borderRadius: '16px',
                                border: '1px solid #333',
                                backgroundColor: '#2a2a2a',
                                color: '#e5e5e5',
                                fontSize: '15px',
                                resize: 'vertical',
                                fontFamily: 'inherit',
                                outline: 'none',
                                transition: 'all 0.2s ease'
                            }}
                        />
                        <button
                            onClick={sendMessage}
                            disabled={!inputMessage.trim() || !selectedModel || isLoading}
                            style={{
                                padding: '16px 24px',
                                background: (!inputMessage.trim() || !selectedModel || isLoading)
                                    ? '#333'
                                    : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '16px',
                                cursor: (!inputMessage.trim() || !selectedModel || isLoading) ? 'not-allowed' : 'pointer',
                                fontSize: '15px',
                                fontWeight: '600',
                                whiteSpace: 'nowrap',
                                transition: 'all 0.2s ease',
                                boxShadow: (!inputMessage.trim() || !selectedModel || isLoading)
                                    ? 'none'
                                    : '0 4px 15px rgba(102, 126, 234, 0.4)'
                            }}
                        >
                            {isLoading ? 'Sending...' : 'Send'}
                        </button>
                    </div>
                </div>
            </div>

            {/* New Chat Name Modal */}
            {showNameModal && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000
                }}>
                    <div style={{
                        backgroundColor: '#1a1a1a',
                        border: '1px solid #333',
                        borderRadius: '16px',
                        padding: '32px',
                        minWidth: '400px',
                        maxWidth: '90vw',
                        boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)'
                    }}>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            marginBottom: '24px'
                        }}>
                            <h2 style={{
                                margin: 0,
                                fontSize: '1.5rem',
                                fontWeight: '600',
                                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                WebkitBackgroundClip: 'text',
                                WebkitTextFillColor: 'transparent'
                            }}>
                                Name Your Chat
                            </h2>
                            <button
                                onClick={closeNewChatModal}
                                style={{
                                    background: 'none',
                                    border: 'none',
                                    color: '#666',
                                    fontSize: '24px',
                                    cursor: 'pointer',
                                    padding: '4px 8px',
                                    borderRadius: '8px'
                                }}
                                onMouseOver={(e) => {
                                    e.target.style.color = '#e5e5e5'
                                    e.target.style.backgroundColor = '#333'
                                }}
                                onMouseOut={(e) => {
                                    e.target.style.color = '#666'
                                    e.target.style.backgroundColor = 'transparent'
                                }}
                            >
                                ×
                            </button>
                        </div>

                        <form onSubmit={handleCreateNamedChat}>
                            <div style={{ marginBottom: '24px' }}>
                                <label style={{
                                    display: 'block',
                                    marginBottom: '8px',
                                    color: '#e5e5e5',
                                    fontSize: '14px',
                                    fontWeight: '500'
                                }}>
                                    Chat Name
                                </label>
                                <input
                                    type="text"
                                    value={newChatName}
                                    onChange={(e) => setNewChatName(e.target.value)}
                                    placeholder="Enter a name for your chat..."
                                    autoFocus
                                    style={{
                                        width: '100%',
                                        padding: '12px 16px',
                                        backgroundColor: '#2a2a2a',
                                        border: '1px solid #333',
                                        borderRadius: '8px',
                                        color: '#e5e5e5',
                                        fontSize: '15px',
                                        outline: 'none',
                                        boxSizing: 'border-box'
                                    }}
                                    onFocus={(e) => {
                                        e.target.style.borderColor = '#667eea'
                                    }}
                                    onBlur={(e) => {
                                        e.target.style.borderColor = '#333'
                                    }}
                                />
                                <div style={{
                                    fontSize: '12px',
                                    color: '#888',
                                    marginTop: '6px'
                                }}>
                                    Leave empty for "New Chat" (default)
                                </div>
                            </div>

                            <div style={{
                                display: 'flex',
                                gap: '12px',
                                justifyContent: 'flex-end'
                            }}>
                                <button
                                    type="button"
                                    onClick={closeNewChatModal}
                                    style={{
                                        padding: '10px 20px',
                                        backgroundColor: 'transparent',
                                        border: '1px solid #333',
                                        borderRadius: '8px',
                                        color: '#e5e5e5',
                                        cursor: 'pointer',
                                        fontSize: '14px'
                                    }}
                                    onMouseOver={(e) => {
                                        e.target.style.backgroundColor = '#333'
                                    }}
                                    onMouseOut={(e) => {
                                        e.target.style.backgroundColor = 'transparent'
                                    }}
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={isCreatingSession}
                                    style={{
                                        padding: '10px 20px',
                                        background: isCreatingSession
                                            ? '#333'
                                            : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                        border: 'none',
                                        borderRadius: '8px',
                                        color: 'white',
                                        cursor: isCreatingSession ? 'not-allowed' : 'pointer',
                                        fontSize: '14px',
                                        fontWeight: '600',
                                        boxShadow: isCreatingSession
                                            ? 'none'
                                            : '0 4px 15px rgba(102, 126, 234, 0.4)'
                                    }}
                                >
                                    {isCreatingSession ? 'Creating...' : 'Create Chat'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* CSS animations */}
            <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
        </div>
    )
} 