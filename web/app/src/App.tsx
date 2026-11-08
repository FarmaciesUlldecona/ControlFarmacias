import { Route, Routes } from 'react-router-dom';
import Layout from './Layout.tsx';
import { PaginaInicio } from './inicio.tsx';
import { PaginaDetalle, PaginaEnConstruccion, PaginaFacturas, PaginaNoEncontrada } from './paginas.tsx';

/** Pantallas de la fase 1. En H3b: cabecera + "En construcción". */
export const PANTALLAS = [
  { ruta: '/', menu: 'Inicio', titulo: 'Resumen del día', subtitulo: 'Estado de facturas, conciliación y documentos de PIO', api: '/api/inicio', bloque: 'inicio' },
  { ruta: '/facturas', menu: 'Facturas', titulo: 'Facturas', subtitulo: 'Facturas normalizadas y PDF sin factura', api: '/api/facturas', bloque: 'facturas' },
  { ruta: '/conciliacion', menu: 'Conciliación', titulo: 'Conciliación', subtitulo: 'Bandeja de facturas frente a albaranes de Farmatic', api: '/api/conciliacion', bloque: 'conciliacionBandeja' },
  { ruta: '/vencimientos', menu: 'Vencimientos', titulo: 'Vencimientos', subtitulo: 'Calendario de vencimientos documentados', api: '/api/vencimientos', bloque: 'vencimientos' },
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
              : p.ruta === '/facturas' ? <PaginaFacturas pantalla={p} /> : <PaginaEnConstruccion pantalla={p} />}
          />
        ))}
        <Route path="/facturas/:id" element={<PaginaDetalle />} />
        <Route path="*" element={<PaginaNoEncontrada />} />
      </Route>
    </Routes>
  );
}
