import { createContext, useContext, useState, useCallback } from 'react';

const ToastContext = createContext(null);

let toastId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((msg, type = 'success', duration = 4000) => {
    const id = ++toastId;
    setToasts(prev => [...prev, { id, msg, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, duration);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast debe usarse dentro de <ToastProvider>');
  return ctx;
}

const TOAST_STYLES = {
  success: { bar: 'bg-emerald-500', icon: '✅', text: 'text-emerald-800', bg: 'bg-emerald-50 border-emerald-200' },
  error:   { bar: 'bg-red-500',     icon: '❌', text: 'text-red-800',     bg: 'bg-red-50 border-red-200' },
  warning: { bar: 'bg-amber-400',   icon: '⚠️', text: 'text-amber-800',   bg: 'bg-amber-50 border-amber-200' },
  info:    { bar: 'bg-blue-500',    icon: 'ℹ️', text: 'text-blue-800',    bg: 'bg-blue-50 border-blue-200' },
};

function ToastContainer({ toasts, removeToast }) {
  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-3 pointer-events-none">
      {toasts.map(t => {
        const s = TOAST_STYLES[t.type] || TOAST_STYLES.info;
        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 border rounded-2xl shadow-xl px-4 py-3 min-w-[280px] max-w-sm animate-slide-in ${s.bg}`}
          >
            <div className={`w-1 self-stretch rounded-full shrink-0 ${s.bar}`} />
            <span className="text-xl mt-0.5 shrink-0">{s.icon}</span>
            <p className={`text-sm font-semibold flex-grow leading-snug ${s.text}`}>{t.msg}</p>
            <button
              onClick={() => removeToast(t.id)}
              className={`text-lg leading-none mt-0.5 opacity-50 hover:opacity-100 transition-opacity shrink-0 ${s.text}`}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
