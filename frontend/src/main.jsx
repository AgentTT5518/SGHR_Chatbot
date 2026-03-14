import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
/* index.css removed — styles live in src/styles/index.css loaded by App.jsx */
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
