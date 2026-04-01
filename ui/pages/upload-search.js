import { useState, useEffect } from 'react';

export default function UploadSearch() {
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  
  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLimit, setSearchLimit] = useState(5);
  const [searchResults, setSearchResults] = useState([]);
  const [expandedResult, setExpandedResult] = useState(null);
  
  // Index status state
  const [indexStatus, setIndexStatus] = useState(null);
  
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000';

  // Load index status on mount and after uploads
  const loadIndexStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/index/status`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setIndexStatus(data);
    } catch (err) {
      console.error('Failed to load index status:', err);
    }
  };

  useEffect(() => {
    loadIndexStatus();
  }, []);

  // Drag and drop handlers
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    const files = [...(e.dataTransfer?.files || [])];
    if (!files.length) return;
    
    await uploadFiles(files);
  };

  const handleFileInput = async (e) => {
    const files = [...(e.target?.files || [])];
    if (!files.length) return;
    
    await uploadFiles(files);
    e.target.value = ''; // Reset input
  };

  const uploadFiles = async (files) => {
    setLoading(true);
    setError(null);
    const results = [];
    
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE}/documents/upload`, {
          method: 'POST',
          body: formData,
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Upload failed: ${errorText}`);
        }
        
        const result = await response.json();
        results.push({ file: file.name, success: true, result });
        
        // Show success toast
        showToast(`✅ ${file.name} uploaded successfully`);
        
      } catch (err) {
        results.push({ file: file.name, success: false, error: err.message });
        showToast(`❌ ${file.name} upload failed: ${err.message}`);
      }
    }
    
    setUploadedFiles(prev => [...results, ...prev]);
    setLoading(false);
    
    // Refresh index status
    await loadIndexStatus();
  };

  const showToast = (message) => {
    // Simple toast implementation - could be enhanced with a proper toast library
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 bg-gray-800 text-white px-4 py-2 rounded-lg shadow-lg z-50';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => document.body.removeChild(toast), 3000);
  };

  const handleSearch = async () => {
    const query = searchQuery.trim();
    if (!query) {
      setSearchResults([]);
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${API_BASE}/documents/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: query, 
          limit: searchLimit 
        }),
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Search failed: ${errorText}`);
      }
      
      const data = await response.json();
      setSearchResults(data.results || []);
      
    } catch (err) {
      setError(err.message);
      setSearchResults([]);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = (index) => {
    setExpandedResult(expandedResult === index ? null : index);
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <h1 className="text-3xl font-bold mb-8">Upload & Search</h1>
      
      {/* Error display */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          Error: {error}
        </div>
      )}
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Upload Card */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold mb-4">📁 Upload Documents</h2>
            
            {/* Drag and Drop Zone */}
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors mb-4 ${
                dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <div className="text-gray-600">
                <p className="text-lg mb-2">Drop files here</p>
                <p className="text-sm">PDF, DOCX, TXT, MD, Images</p>
              </div>
              
              <div className="mt-4">
                <label className="inline-block px-4 py-2 bg-blue-500 text-white rounded-lg cursor-pointer hover:bg-blue-600">
                  Choose Files
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.gif"
                    onChange={handleFileInput}
                    className="hidden"
                  />
                </label>
              </div>
            </div>
            
            {/* Upload Status */}
            {loading && (
              <div className="text-center text-blue-600">
                <div className="animate-spin inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full mr-2"></div>
                Uploading...
              </div>
            )}
            
            {/* Recent Uploads */}
            {uploadedFiles.length > 0 && (
              <div className="mt-4">
                <h3 className="font-medium mb-2">Recent Uploads</h3>
                <div className="space-y-2 max-h-32 overflow-y-auto">
                  {uploadedFiles.slice(0, 5).map((upload, idx) => (
                    <div key={idx} className={`text-sm p-2 rounded ${
                      upload.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                    }`}>
                      {upload.success ? '✅' : '❌'} {upload.file}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Chunk Settings Display */}
            {indexStatus && (
              <div className="mt-4 p-3 bg-gray-50 rounded text-sm">
                <p><strong>Current Settings:</strong></p>
                <p>Chunk Size: {indexStatus.chunk_size}</p>
                <p>Overlap: {indexStatus.chunk_overlap}</p>
              </div>
            )}
          </div>
        </div>
        
        {/* Search Card */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold mb-4">🔍 Search Documents</h2>
            
            {/* Search Input */}
            <div className="space-y-4">
              <div>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Enter your search query..."
                  className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
              </div>
              
              <div className="flex gap-2">
                <select
                  value={searchLimit}
                  onChange={(e) => setSearchLimit(parseInt(e.target.value))}
                  className="px-3 py-2 border rounded-lg"
                >
                  <option value={3}>Top 3</option>
                  <option value={5}>Top 5</option>
                  <option value={10}>Top 10</option>
                  <option value={20}>Top 20</option>
                </select>
                
                <button
                  onClick={handleSearch}
                  disabled={!searchQuery.trim() || loading}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300"
                >
                  Search
                </button>
              </div>
              
              {searchQuery && (
                <button
                  onClick={() => { setSearchQuery(''); setSearchResults([]); }}
                  className="w-full px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Clear
                </button>
              )}
            </div>
            
            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="mt-6">
                <h3 className="font-medium mb-3">Results ({searchResults.length})</h3>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {searchResults.map((result, idx) => (
                    <div key={idx} className="border rounded-lg p-3">
                      <div className="flex justify-between items-start">
                        <h4 className="font-medium text-blue-600 text-sm">
                          {result.document_name}
                        </h4>
                        <span className="text-xs text-gray-500">
                          {(result.similarity_score * 100).toFixed(1)}%
                        </span>
                      </div>
                      
                      <p className="text-sm text-gray-600 mt-1">
                        {(result.content || '').substring(0, 150)}
                        {result.content && result.content.length > 150 ? '...' : ''}
                      </p>
                      
                      <button
                        onClick={() => toggleExpanded(idx)}
                        className="text-xs text-blue-500 hover:text-blue-700 mt-2"
                      >
                        {expandedResult === idx ? 'Show less' : 'Show more'}
                      </button>
                      
                      {expandedResult === idx && (
                        <div className="mt-2 p-2 bg-gray-50 rounded text-sm">
                          {result.content}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        
        {/* Index Status Panel */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-semibold mb-4">📊 Index Status</h2>
            
            {indexStatus ? (
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Documents:</span>
                  <span className="font-medium">{indexStatus.documents}</span>
                </div>
                
                <div className="flex justify-between">
                  <span className="text-gray-600">Chunks:</span>
                  <span className="font-medium">{indexStatus.chunks}</span>
                </div>
                
                <div className="flex justify-between">
                  <span className="text-gray-600">Last Ingest:</span>
                  <span className="font-medium text-sm">
                    {indexStatus.last_ingest 
                      ? new Date(indexStatus.last_ingest).toLocaleDateString()
                      : 'None'
                    }
                  </span>
                </div>
                
                <hr className="my-3" />
                
                <div className="text-sm text-gray-600">
                  <p><strong>Embedding Model:</strong></p>
                  <p className="break-words">{indexStatus.embed_model}</p>
                </div>
                
                <div className="text-sm text-gray-600">
                  <p><strong>Chunk Configuration:</strong></p>
                  <p>Size: {indexStatus.chunk_size} words</p>
                  <p>Overlap: {indexStatus.chunk_overlap} words</p>
                </div>
                
                <button
                  onClick={loadIndexStatus}
                  className="w-full mt-4 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm"
                >
                  Refresh Status
                </button>
              </div>
            ) : (
              <div className="text-center text-gray-500">
                <div className="animate-spin inline-block w-6 h-6 border-2 border-current border-t-transparent rounded-full"></div>
                <p className="mt-2">Loading status...</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
