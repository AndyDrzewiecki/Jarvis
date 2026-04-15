import { useState } from 'react'
import StatusBar from './components/StatusBar'
import SpecialistsPanel from './components/SpecialistsPanel'
import EnginesPanel from './components/EnginesPanel'
import KnowledgeLakePanel from './components/KnowledgeLakePanel'
import DecisionsPanel from './components/DecisionsPanel'
import HouseholdStatePanel from './components/HouseholdStatePanel'
import PreferencesPanel from './components/PreferencesPanel'
import BlackboardPanel from './components/BlackboardPanel'

const TABS = [
  { id: 'specialists',     label: 'Specialists',      icon: '🤖' },
  { id: 'engines',         label: 'Engines',          icon: '⚙️' },
  { id: 'knowledge',       label: 'Knowledge Lake',   icon: '🌊' },
  { id: 'decisions',       label: 'Decisions',        icon: '🔍' },
  { id: 'household',       label: 'Household State',  icon: '🏠' },
  { id: 'preferences',     label: 'Preferences',      icon: '⚙️' },
  { id: 'blackboard',      label: 'Blackboard',       icon: '📋' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('specialists')

  return (
    <div className="min-h-screen flex flex-col bg-jarvis-bg">
      <StatusBar />

      {/* Tab nav */}
      <nav className="bg-jarvis-bg border-b border-jarvis-border px-4 overflow-x-auto">
        <div className="flex gap-0 min-w-max">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-1.5 px-4 py-3 text-xs font-medium whitespace-nowrap
                border-b-2 transition-colors
                ${activeTab === tab.id
                  ? 'text-jarvis-accent border-jarvis-accent'
                  : 'text-jarvis-dim border-transparent hover:text-gray-300 hover:border-jarvis-border'}
              `}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Panel content */}
      <main className="flex-1 p-4 max-w-screen-2xl w-full mx-auto">
        {activeTab === 'specialists'  && <SpecialistsPanel />}
        {activeTab === 'engines'      && <EnginesPanel />}
        {activeTab === 'knowledge'    && <KnowledgeLakePanel />}
        {activeTab === 'decisions'    && <DecisionsPanel />}
        {activeTab === 'household'    && <HouseholdStatePanel />}
        {activeTab === 'preferences'  && <PreferencesPanel />}
        {activeTab === 'blackboard'   && <BlackboardPanel />}
      </main>

      <footer className="text-center text-jarvis-dim text-xs py-3 border-t border-jarvis-border">
        Jarvis v0.4.0 · Phase 4A Web Dashboard · <span className="text-jarvis-accent">192.168.111.28:8000</span>
      </footer>
    </div>
  )
}
