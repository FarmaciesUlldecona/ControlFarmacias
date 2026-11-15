import { Route, Routes } from 'react-router-dom';
import Layout from './Layout.tsx';
import { PaginaInicio } from './inicio.tsx';
import { PaginaDetalle } from './detalle.tsx';
import { PaginaFacturas } from './facturas.tsx';
import { PaginaEnConstruccion, PaginaNoEncontrada } from './paginas.tsx';
import { PaginaTrabajadora, PaginaTrabajadores } from './trabajadores.tsx';
import { PaginaCalendario } from './calendario.tsx';
import { PaginaGuardias } from './guardias.tsx';
import { PaginaVencimientos } from './vencimientos.tsx';

/** Pantallas de la fase 1. En H3b: cabecera + "En construcción". */
export const PANTALLAS = [
  { ruta: '/', menu: 'Inicio', titulo: 'Resumen del día', subtitulo: 'Estado de facturas, conciliación y documentos de PIO', api: '/api/inicio', bloque: 'inicio' },
  { ruta: '/facturas', menu: 'Facturas', titulo: 'Facturas', subtitulo: 'Facturas normalizadas y PDF sin factura', api: '/api/facturas', bloque: 'facturas' },
  { ruta: '/conciliacion', menu: 'Conciliación', titulo: 'Conciliación', subtitulo: 'Bandeja de facturas frente a albaranes de Farmatic', api: '/api/conciliacion', bloque: 'conciliacionBandeja' },
  // H6: lista de vencimientos con estado de pago (marcas en /api/pagos/*).
  { ruta: '/vencimientos', menu: 'Vencimientos', titulo: 'Vencimientos', subtitulo: 'Vencimientos de PIO y su estado de pago', api: '/api/pagos/vencimientos', bloque: 'vencimientos' },
  { ruta: '/cashflow', menu: 'Cashflow', titulo: 'Cashflow', subtitulo: 'Vencimientos agrupados por semana', api: '/api/cashflow', bloque: 'cashflowSemanas' },
  { ruta: '/proveedores', menu: 'Proveedores', titulo: 'Proveedores', subtitulo: 'Estado por proveedor y documentos por estado', api: '/api/proveedores', bloque: 'proveedores' },
  { ruta: '/configuracion', menu: 'Configuración', titulo: 'Configuración', subtitulo: 'Interruptores y parámetros del motor (solo lectura)', api: '/api/configuracion', bloque: 'configuracion' },
] as const;

export type Pantalla = (typeof PANTALLAS)[number];

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {PANTALLAS.map((p) => (
          <Route
            key={p.ruta}
            path={p.ruta}
            element={p.ruta === '/' ? <PaginaInicio />
              : p.ruta === '/facturas' ? <PaginaFacturas />
              : p.ruta === '/vencimientos' ? <PaginaVencimientos /> : <PaginaEnConstruccion pantalla={p} />}
          />
        ))}
        <Route path="/facturas/:id" element={<PaginaDetalle />} />
        {/* TA1: módulo Trabajadores (datos de ejemplo en memoria; REAL: pendiente de conexión T1). */}
        <Route path="/trabajadores" element={<PaginaTrabajadores />} />
        {/* TA2: calendario (ruta fija: tiene prioridad sobre /trabajadores/:id). */}
        <Route path="/trabajadores/calendario" element={<PaginaCalendario />} />
        {/* TA3: guardias y festivos (ruta fija, como el calendario). */}
        <Route path="/trabajadores/guardias" element={<PaginaGuardias />} />
        <Route path="/trabajadores/:id" element={<PaginaTrabajadora />} />
        <Route path="*" element={<PaginaNoEncontrada />} />
      </Route>
    </Routes>
  );
}
