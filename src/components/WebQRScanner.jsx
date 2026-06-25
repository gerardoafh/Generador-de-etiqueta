import React, { useEffect, useRef } from 'react';
import { Html5QrcodeScanner } from 'html5-qrcode';

const WebQRScanner = ({ onScanSuccess, onClose }) => {
  const scannerRef = useRef(null);

  useEffect(() => {
    // Generar un ID único por si acaso
    const scannerId = "qr-reader";

    // Configuración del escáner
    const config = {
      fps: 10,
      qrbox: { width: 250, height: 250 },
      aspectRatio: 1.0,
      videoConstraints: {
        facingMode: "environment"
      },
      supportedScanTypes: [0] // 0 = QR_CODE (Html5QrcodeScanType.SCAN_TYPE_CAMERA)
    };

    const scanner = new Html5QrcodeScanner(scannerId, config, false);
    
    // Callback para evitar que siga escaneando tras el primer éxito
    let isScanned = false;
    const onScan = (decodedText) => {
      // Ignorar silenciosamente QRs que no tengan la palabra FECHA
      if (!decodedText.toUpperCase().includes("FECHA")) {
        return;
      }

      if (!isScanned) {
        isScanned = true;
        // Limpiar el escáner
        scanner.clear().catch(console.error);
        
        // Llamar a la función del padre
        onScanSuccess(decodedText);
      }
    };

    const onScanError = (errorMessage) => {
      // Html5QrcodeScanner dispara errores constantemente cuando no hay QR
      // Los ignoramos silenciosamente
    };

    scanner.render(onScan, onScanError);
    scannerRef.current = scanner;

    return () => {
      // Limpiar al desmontar
      if (scannerRef.current) {
        scannerRef.current.clear().catch(console.error);
      }
    };
  }, [onScanSuccess]);

  return (
    <div className="fixed inset-0 bg-slate-900/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl animate-fade-in-up">
        {/* Header del modal */}
        <div className="bg-slate-800 p-4 flex justify-between items-center text-white">
          <h3 className="font-bold flex items-center gap-2">
            <span className="text-xl">📷</span> Escanear Etiqueta
          </h3>
          <button 
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-700 hover:bg-red-500 transition-colors font-bold"
          >
            ✕
          </button>
        </div>

        {/* Contenedor de la cámara */}
        <div className="p-4 bg-slate-100">
          <div id="qr-reader" className="rounded-xl overflow-hidden shadow-inner bg-black"></div>
        </div>
        
        {/* Instrucciones */}
        <div className="p-4 bg-white text-center text-slate-500 text-sm">
          <p>Apunta la cámara al código QR de la etiqueta.</p>
          <p className="mt-1 font-semibold text-slate-700">La acción seleccionada se aplicará automáticamente.</p>
        </div>
      </div>
    </div>
  );
};

export default WebQRScanner;
