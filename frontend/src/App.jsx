import { useState, useEffect } from 'react'

function App() {
  const [health, setHealth] = useState('Loading...')

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then(res => res.json())
      .then(data => setHealth(data.status))
      .catch(err => setHealth('API Offline'))
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-gray-800 rounded-lg shadow-lg p-6">
        <h1 className="text-2xl font-bold text-white mb-4">Civic Voice Agent</h1>
        <div className="bg-gray-900 rounded p-4 border border-gray-700">
          <p className="text-gray-300 text-sm mb-1">Backend API Status</p>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${health === 'ok' ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="font-mono text-green-400">{health}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
