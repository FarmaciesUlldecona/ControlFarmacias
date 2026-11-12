import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useApi, type EstadoApi } from './api.ts';

interface Enlace { a: string; texto: string }
interface Grupo { titulo: string; enlaces: Enlace[]; proximamente: string[] }

// Mismo menú agrupado que las maquetas (web/docs/maquetas/Main.dc.html).
const MENU: Grupo[] = [
  {
    titulo: 'Finanzas',
    enlaces: [
      { a: '/', texto: 'Inicio' },
      { a: '/facturas', texto: 'Facturas' },
      { a: '/conciliacion', texto: 'Conciliación' },
      { a: '/vencimientos', texto: 'Vencimientos' },
      { a: '/cashflow', texto: 'Cashflow' },
    ],
    proximamente: [],
  },
  { titulo: 'Negocio', enlaces: [], proximamente: ['Compras', 'Stock', 'Ventas', 'Clientes'] },
  // TA1: Trabajadores activo (datos de ejemplo hasta T1).
  { titulo: 'Equipo', enlaces: [{ a: '/trabajadores', texto: 'Trabajadores' }], proximamente: [] },
  {
    titulo: 'General',
    enlaces: [
      { a: '/proveedores', texto: 'Proveedores' },
      { a: '/configuracion', texto: 'Configuración' },
    ],
    proximamente: [],
  },
];

export default function Layout() {
  const estado = useApi<EstadoApi>('/api/estado');
  const [abierto, setAbierto] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setAbierto(false), [pathname]);

  const modo = estado.estado === 'ok' ? estado.datos.modo : null;
  const usuario = estado.estado === 'ok' ? estado.datos.usuario : null;

  return (
    <div className="app">
      <aside className="lateral">{/* .lateral: fondo de altura completa; .lateral-interior: contenido fijo al desplazar */}
       <div className="lateral-interior">
        <div className="lateral-cabecera">
          <div className="marca"><span className="marca-logo" aria-hidden="true">CF</span>ControlFarmacias</div>
          <button
            type="button"
            className="boton-menu"
            aria-expanded={abierto}
            aria-controls="menu-principal"
            onClick={() => setAbierto((v) => !v)}
          >
            {abierto ? 'Cerrar' : 'Menú'}
          </button>
        </div>
        <div className={abierto ? 'lateral-cuerpo abierto' : 'lateral-cuerpo'}>
          <div className="farmacia">
            <span className="tenue">Farmacia</span>
            <strong>PIO</strong>
            {/* TA1 (decisión T0): RITA solo en el módulo Trabajadores. */}
            <span className="tenue" data-rita>{pathname.startsWith('/trabajadores') ? 'RITA: solo en Trabajadores' : 'RITA: no habilitada'}</span>
          </div>
          <nav id="menu-principal" className="menu" aria-label="Menú principal">
            {MENU.map((g) => (
              <div key={g.titulo} className="menu-grupo">
                <span className="menu-titulo">{g.titulo}</span>
                {g.enlaces.map((e) => (
                  <NavLink key={e.a} to={e.a} end={e.a === '/'} className={({ isActive }) => (isActive ? 'activo' : undefined)}>
                    {e.texto}
                  </NavLink>
                ))}
                {g.proximamente.map((p) => (
                  <span key={p} className="menu-proximamente" aria-disabled="true">
                    {p}<span className="chip-proximamente">Próximamente</span>
                  </span>
                ))}
              </div>
            ))}
          </nav>
          <div className="pie" data-modo={modo ?? ''}>
            <div className="sesion">
              <span><span className="tenue">Sesión de</span> <strong>{usuario ?? 'Pío'}</strong></span>
              {/* Formulario POST sin JavaScript: el servidor borra la sesión y vuelve a la pantalla de acceso. */}
              <form method="post" action="/api/logout">
                <button type="submit" className="boton-salir">Salir</button>
              </form>
            </div>
            Fase 1 · solo lectura
            <br />
            {modo === 'FIXTURES' && <span>Datos ficticios</span>}
            {modo === 'REAL' && <span>Datos reales · cf_lectura</span>}
            {modo === null && <span>Conectando con la API local…</span>}
          </div>
        </div>
       </div>
      </aside>
      <main className="principal">
        <Outlet />
      </main>
    </div>
  );
}
