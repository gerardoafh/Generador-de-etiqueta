// Shim — redirige a useToast.jsx que contiene JSX (OXC no parsea JSX en .js).
// IMPORTANTE: No eliminar ni vaciar este archivo; es necesario para la resolución de módulos de Vite.
export { ToastProvider, useToast } from './useToast.jsx';
