import { useState, useCallback } from 'react';

/**
 * Hook para manejar un modal de confirmación estilizado.
 * Uso:
 *   const { confirmModal, requestConfirm } = useConfirm();
 *   const ok = await requestConfirm({ title: '...', message: '...' });
 *   if (ok) { ... }
 *   // Añadir {confirmModal} en el JSX del componente.
 */
export function useConfirm() {
  const [state, setState] = useState(null);

  const requestConfirm = useCallback(({ title, message, confirmText = 'Confirmar', danger = true }) => {
    return new Promise(resolve => {
      setState({ title, message, confirmText, danger, resolve });
    });
  }, []);

  const handleResponse = (result) => {
    state?.resolve(result);
    setState(null);
  };

  const confirmModal = state ? (
    <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={() => handleResponse(false)}
      />
      <div className="relative bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md flex flex-col gap-4 animate-scale-in">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl shrink-0 ${state.danger ? 'bg-red-100' : 'bg-blue-100'}`}>
          {state.danger ? '🗑️' : '❓'}
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-800 mb-1">{state.title}</h3>
          <p className="text-slate-500 text-sm leading-relaxed">{state.message}</p>
        </div>
        <div className="flex gap-3 pt-2">
          <button
            onClick={() => handleResponse(false)}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-semibold hover:bg-slate-50 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={() => handleResponse(true)}
            className={`flex-1 px-4 py-2.5 rounded-xl text-white font-bold transition-colors ${state.danger ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-600 hover:bg-blue-700'}`}
          >
            {state.confirmText}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { confirmModal, requestConfirm };
}
