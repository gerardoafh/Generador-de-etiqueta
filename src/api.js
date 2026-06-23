// src/api.js
// Punto central de configuración del servidor backend.
// Para cambiar el servidor, define VITE_API_URL en un archivo .env
export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * Wrapper de fetch que agrega automáticamente la URL base del servidor.
 * @param {string} path  - Ruta del endpoint, ej: "/parts"
 * @param {RequestInit} opts - Opciones de fetch (method, headers, body, etc.)
 */
export const apiFetch = (path, opts = {}) =>
  fetch(`${API_BASE}${path}`, opts);
