import { useState } from 'react';
import MainMenu from './components/MainMenu';
import PartManager from './components/PartManager';
import DryingRoom from './components/DryingRoom';
import PrintQueue from './components/PrintQueue';
import ProductionReport from './components/ProductionReport';
import { ToastProvider } from './hooks/useToast.jsx';
import './App.css';

function App() {
  const [view, setView] = useState('menu');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Navega a la nueva vista y cierra el menú hamburguesa automáticamente
  const changeView = (newView) => {
    setView(newView);
    setIsMobileMenuOpen(false);
  };

  return (
    <ToastProvider>
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Barra de Navegación Global (Visible en todos los módulos excepto el Menú Principal) */}
      {view !== 'menu' && (
        <header className="bg-slate-900 text-white sticky top-0 z-50 shadow-lg">
          <div className="max-w-[1400px] mx-auto px-4 h-16 flex items-center justify-between">
            
            {/* Logo y Título */}
            <div 
              className="flex items-center gap-3 cursor-pointer select-none" 
              onClick={() => changeView('menu')}
            >
              <div className="bg-white px-2 py-1 rounded-lg font-extrabold text-xl leading-none">
                <span className="text-blue-600">C</span><span className="text-red-600">w</span>
              </div>
              <span className="font-bold tracking-wide hidden sm:block">Sistema de Gestión</span>
            </div>

            {/* Navegación Desktop */}
            <nav className="hidden md:flex gap-2">
              <button onClick={() => changeView('parts')} className={`px-3 py-2 rounded-lg font-medium text-sm transition-colors ${view === 'parts' ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}>⚙️ Partes</button>
              <button onClick={() => changeView('queue')} className={`px-3 py-2 rounded-lg font-medium text-sm transition-colors ${view === 'queue' ? 'bg-green-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}>🖨️ Cola</button>
              <button onClick={() => changeView('drying')} className={`px-3 py-2 rounded-lg font-medium text-sm transition-colors ${view === 'drying' ? 'bg-orange-500 text-white' : 'text-slate-300 hover:bg-slate-800'}`}>♨️ Secado</button>
              <button onClick={() => changeView('report')} className={`px-3 py-2 rounded-lg font-medium text-sm transition-colors ${view === 'report' ? 'bg-purple-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}>📊 Reporte</button>
            </nav>

            {/* Botón Menú Hamburguesa (Mobile) */}
            <button 
              className="md:hidden text-2xl p-2 rounded-lg bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              {isMobileMenuOpen ? '✖' : '☰'}
            </button>
          </div>

          {/* Menú Desplegable Mobile */}
          {isMobileMenuOpen && (
            <div className="md:hidden absolute top-16 left-0 w-full bg-slate-900 border-t border-slate-800 shadow-2xl flex flex-col">
              <button onClick={() => changeView('menu')} className="p-4 text-left font-medium border-b border-slate-800 hover:bg-slate-800">🏠 Menú Principal</button>
              <button onClick={() => changeView('parts')} className={`p-4 text-left font-medium border-b border-slate-800 hover:bg-slate-800 ${view === 'parts' ? 'text-blue-400 bg-slate-800' : 'text-slate-300'}`}>⚙️ Gestionar Partes</button>
              <button onClick={() => changeView('queue')} className={`p-4 text-left font-medium border-b border-slate-800 hover:bg-slate-800 ${view === 'queue' ? 'text-green-400 bg-slate-800' : 'text-slate-300'}`}>🖨️ Cola de Impresión</button>
              <button onClick={() => changeView('drying')} className={`p-4 text-left font-medium border-b border-slate-800 hover:bg-slate-800 ${view === 'drying' ? 'text-orange-400 bg-slate-800' : 'text-slate-300'}`}>♨️ Cuarto de Secado</button>
              <button onClick={() => changeView('report')} className={`p-4 text-left font-medium hover:bg-slate-800 ${view === 'report' ? 'text-purple-400 bg-slate-800' : 'text-slate-300'}`}>📊 Reporte de Producción</button>
            </div>
          )}
        </header>
      )}

      <div className="flex-grow">
        {view === 'menu' && <MainMenu setView={changeView} />}
        {view === 'parts' && <PartManager goBack={() => changeView('menu')} />}
        {view === 'drying' && <DryingRoom goBack={() => changeView('menu')} />}
        {view === 'queue' && <PrintQueue goBack={() => changeView('menu')} />}
        {view === 'report' && <ProductionReport goBack={() => changeView('menu')} />}
      </div>
    </div>
    </ToastProvider>
  );
}

export default App;
