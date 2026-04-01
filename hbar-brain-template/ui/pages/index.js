import { useEffect, useState } from 'react'

export default function Home() {
  const [apiStatus, setApiStatus] = useState('checking...')
  const [apiData, setApiData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const checkAPI = async () => {
      try {
        const response = await fetch(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
        if (response.ok) {
          const data = await response.json()
          setApiData(data)
          setApiStatus('✅ Connected')
        } else {
          setApiStatus('❌ API Error')
        }
      } catch (err) {
        setApiStatus('❌ Connection Failed')
        setError(err.message)
      }
    }

    checkAPI()
  }, [])

  return (
    <div style={{
      minHeight: '100vh',
      height: '100vh',
      backgroundColor: '#0a0a0a',
      color: '#e5e5e5',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      margin: 0,
      padding: 0,
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: '100vw',
      overflowY: 'auto'
    }}>
      {/* Top Navigation */}
      <nav style={{
        backgroundColor: '#1a1a1a',
        borderBottom: '1px solid #333',
        padding: '16px 0',
        position: 'sticky',
        top: 0,
        zIndex: 100,
        backdropFilter: 'blur(10px)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.3)'
      }}>
        <div style={{
          maxWidth: '1200px',
          margin: '0 auto',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{
            fontSize: '1.5rem',
            fontWeight: 'bold',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            🤖 LLM Assistant
          </div>

          <a
            href="/chat"
            style={{
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              padding: '12px 24px',
              borderRadius: '12px',
              textDecoration: 'none',
              fontSize: '16px',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 15px rgba(102, 126, 234, 0.4)',
              transition: 'all 0.3s ease',
              border: 'none'
            }}
            onMouseOver={(e) => {
              e.target.style.transform = 'translateY(-2px)'
              e.target.style.boxShadow = '0 8px 25px rgba(102, 126, 234, 0.6)'
            }}
            onMouseOut={(e) => {
              e.target.style.transform = 'translateY(0)'
              e.target.style.boxShadow = '0 4px 15px rgba(102, 126, 234, 0.4)'
            }}
          >
            💬 Chat Interface
          </a>
        </div>
      </nav>

      {/* Main Content */}
      <div style={{
        padding: '60px 24px',
        maxWidth: '1200px',
        margin: '0 auto'
      }}>
        {/* Hero Section */}
        <header style={{
          marginBottom: '60px',
          textAlign: 'center'
        }}>
          <h1 style={{
            fontSize: '4rem',
            fontWeight: '800',
            marginBottom: '20px',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            lineHeight: '1.1'
          }}>
            Private LLM Assistant
          </h1>
          <p style={{
            color: '#a0a0a0',
            fontSize: '1.4rem',
            maxWidth: '600px',
            margin: '0 auto',
            lineHeight: '1.6'
          }}>
            Powerful AI chat with document processing, vector search, and RAG capabilities
          </p>
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '12px',
            marginTop: '30px',
            flexWrap: 'wrap'
          }}>
            <span style={{
              backgroundColor: '#1a1a1a',
              color: '#00d4aa',
              padding: '8px 16px',
              borderRadius: '20px',
              fontSize: '14px',
              fontWeight: '500',
              border: '1px solid #00d4aa30'
            }}>
              FastAPI Backend
            </span>
            <span style={{
              backgroundColor: '#1a1a1a',
              color: '#61dafb',
              padding: '8px 16px',
              borderRadius: '20px',
              fontSize: '14px',
              fontWeight: '500',
              border: '1px solid #61dafb30'
            }}>
              Next.js Frontend
            </span>
            <span style={{
              backgroundColor: '#1a1a1a',
              color: '#336791',
              padding: '8px 16px',
              borderRadius: '20px',
              fontSize: '14px',
              fontWeight: '500',
              border: '1px solid #33679130'
            }}>
              PostgreSQL + pgvector
            </span>
          </div>
        </header>

        {/* Service Status Card */}
        <div style={{
          backgroundColor: '#1a1a1a',
          padding: '40px',
          borderRadius: '20px',
          marginBottom: '30px',
          border: '1px solid #333',
          boxShadow: '0 10px 40px rgba(0,0,0,0.3)'
        }}>
          <h2 style={{
            color: '#e5e5e5',
            marginBottom: '30px',
            fontSize: '1.8rem',
            fontWeight: '700',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            🔗 Service Status
          </h2>

          <div style={{
            display: 'grid',
            gap: '20px'
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '20px',
              backgroundColor: '#0f0f0f',
              borderRadius: '12px',
              border: '1px solid #2a2a2a'
            }}>
              <span style={{
                fontSize: '16px',
                fontWeight: '500',
                color: '#b0b0b0'
              }}>
                API Connection
              </span>
              <span style={{
                color: apiStatus.includes('✅') ? '#00d4aa' : '#ff6b6b',
                fontWeight: '600',
                fontSize: '16px',
                padding: '6px 12px',
                backgroundColor: apiStatus.includes('✅') ? '#00d4aa20' : '#ff6b6b20',
                borderRadius: '8px',
                border: `1px solid ${apiStatus.includes('✅') ? '#00d4aa40' : '#ff6b6b40'}`
              }}>
                {apiStatus}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '20px',
              backgroundColor: '#0f0f0f',
              borderRadius: '12px',
              border: '1px solid #2a2a2a'
            }}>
              <span style={{
                fontSize: '16px',
                fontWeight: '500',
                color: '#b0b0b0'
              }}>
                API Endpoint
              </span>
              <code style={{
                backgroundColor: '#2a2a2a',
                color: '#e5e5e5',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '14px',
                fontFamily: 'JetBrains Mono, Monaco, monospace'
              }}>
                {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
              </code>
            </div>
          </div>

          {error && (
            <div style={{
              backgroundColor: '#2a1a1a',
              color: '#ff6b6b',
              padding: '20px',
              borderRadius: '12px',
              fontSize: '14px',
              marginTop: '20px',
              border: '1px solid #ff6b6b30'
            }}>
              <strong>Connection Error:</strong> {error}
            </div>
          )}
        </div>

        {/* API Response Card */}
        {apiData && (
          <div style={{
            backgroundColor: '#1a1a1a',
            padding: '40px',
            borderRadius: '20px',
            border: '1px solid #333',
            boxShadow: '0 10px 40px rgba(0,0,0,0.3)'
          }}>
            <h2 style={{
              color: '#e5e5e5',
              marginBottom: '30px',
              fontSize: '1.8rem',
              fontWeight: '700',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              📊 API Response
            </h2>
            <div style={{
              backgroundColor: '#0a0a0a',
              borderRadius: '16px',
              overflow: 'hidden',
              border: '1px solid #2a2a2a'
            }}>
              <div style={{
                backgroundColor: '#1a1a1a',
                padding: '16px 24px',
                borderBottom: '1px solid #2a2a2a',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#ff6b6b' }}></div>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#ffd93d' }}></div>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#6bcf7f' }}></div>
                <span style={{ marginLeft: '12px', fontSize: '14px', color: '#888' }}>api-response.json</span>
              </div>
              <pre style={{
                color: '#e5e5e5',
                padding: '30px',
                margin: 0,
                overflow: 'auto',
                fontSize: '14px',
                fontFamily: 'JetBrains Mono, Monaco, monospace',
                lineHeight: '1.6',
                backgroundColor: 'transparent'
              }}>
                {JSON.stringify(apiData, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer style={{
        textAlign: 'center',
        padding: '40px 24px',
        color: '#666',
        fontSize: '14px',
        borderTop: '1px solid #2a2a2a',
        backgroundColor: '#1a1a1a'
      }}>
        <p>🐳 Running in Docker • Built with ❤️ using FastAPI, Next.js & PostgreSQL</p>
      </footer>
    </div>
  )
} 