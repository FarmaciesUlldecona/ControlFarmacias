-- Migracion 36 (R20, DECISION DE PIO, 2026-11-19): una linea del PDF casa con la suma de su albaran EXACTO y su
-- variante con LETRA FINAL (08X99999 + 08X99999A), de la misma recepcion, como R17 (migracion 24). Diseno:
-- pruebas/auditoria_r20/DISENO.md. Caso real: 08013495 / 08D79747 = 77,49 + 40,76 (recepcion 54736).
-- - Redefine public.cf_linea_r17_valida con la misma firma: acepta la pareja R17 de la 24 (sin cambios) o la pareja
--   R20. No regenera cf_persistir_conciliacion (30): el rechazo sigue siendo LINEA_R17_NO_VALIDA. create or replace
--   conserva la ACL de la 24 (solo el propietario).
-- - R20: cargo de la propia factura; exactamente 2 detalles; los dos albaranes existen con PUC y cada detalle aplica
--   su PUC; ninguno con numeracion interna; uno con el numero exacto de la linea y otro 08X99999 + una letra; misma
--   farmacia y misma recepcion (no nula); mismo proveedor (R9); las dos fechas a +-15 dias de la linea (la BD SI lo
--   comprueba en R20, decision de Pio); suma dentro de 0,05.
-- - Marca y conmutador: cf_configuracion.conciliacion_r20 (default true). El codigo usa R20 solo si la columna existe
--   y vale true; false apaga R20 sin rollback (decisiones de Pio). Es el unico dato que cambia: el valor de la columna
--   en la fila de configuracion.
-- No nombra el rol del sistema (la autorizacion vigente es solo para la 38). Idempotente. Requiere la 35.
begin;

do $$
begin
    if to_regclass('public.vencimientos_marcas_pago') is null then
        raise exception 'MIGRACION_35_AUSENTE';
    end if;
end;
$$;

alter table public.cf_configuracion add column if not exists conciliacion_r20 boolean not null default true;
comment on column public.cf_configuracion.conciliacion_r20 is
    'R20 (migracion 36): el codigo casa una linea con su albaran exacto + su variante con letra final solo si esta '
    'columna existe y vale true; false apaga R20 sin rollback (decision de Pio, 2026-11-19).';

create or replace function public.cf_linea_r17_valida(
    p_factura_id uuid,
    p_linea text,
    p_detalles jsonb,
    p_todos jsonb
)
returns boolean
language plpgsql
stable
set search_path = public
as $$
declare
    e public.facturas_albaranes_extraidos%rowtype;
    a public.albaranes%rowtype;
    b public.albaranes%rowtype;
    v_n integer;
    v_internos integer;
    v_doc text;
    v_op text;
    v_op_b text;
begin
    if p_linea is null or p_linea !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       or jsonb_typeof(p_detalles) <> 'array' or jsonb_array_length(p_detalles) <> 2 then
        return false;
    end if;
    select * into e from public.facturas_albaranes_extraidos where id = p_linea::uuid;
    if e.id is null or e.factura_id <> p_factura_id or e.importe_total is null
       or e.tipo_movimiento is distinct from 'CARGO' then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_todos) d
     where d->>'factura_albaran_extraido_id' = p_linea;
    if v_n <> 2 then
        return false;
    end if;
    -- Cada detalle: un albaran existente con PUC y el PUC como importe aplicado.
    select count(*), count(*) filter (where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$')
      into v_n, v_internos
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where x.importe_puc is not null
       and (d->>'importe_aplicado')::numeric = x.importe_puc;
    if v_n <> 2 then
        return false;
    end if;
    v_doc := regexp_replace(upper(coalesce(e.numero_albaran, '')), '[^A-Z0-9]', '', 'g');
    if v_doc = '' then
        return false;
    end if;

    if v_internos = 1 then
        -- R17 (24, sin cambios): el albaran de su numero (exacto o letra final) + 1 interno de la misma recepcion.
        select x.* into a
          from jsonb_array_elements(p_detalles) d
          join public.albaranes x
            on x.farmacia = d->>'albaran_farmacia'
           and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
         where upper(btrim(x.numero_albaran)) !~ '^[A-Z][0-9]{6}/[0-9]{4}$';
        select x.* into b
          from jsonb_array_elements(p_detalles) d
          join public.albaranes x
            on x.farmacia = d->>'albaran_farmacia'
           and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
         where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$';
        if a.id_contador = b.id_contador or a.farmacia <> b.farmacia
           or a.id_recepcion is null or a.id_recepcion is distinct from b.id_recepcion
           or public.cf_id_proveedor_comparable(a.id_proveedor)
              is distinct from public.cf_id_proveedor_comparable(b.id_proveedor) then
            return false;
        end if;
        v_op := regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g');
        if not (v_op = v_doc or (v_op ~ '^08[A-Z][0-9]{5}[A-Z]$' and left(v_op, 8) = v_doc)) then
            return false;
        end if;
        return abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500;
    end if;

    if v_internos <> 0 or e.fecha_albaran is null then
        return false;
    end if;
    -- R20 (36): A con el numero exacto de la linea y B su variante con una letra final.
    select x.* into a
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g') = v_doc;
    select x.* into b
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g') ~ '^08[A-Z][0-9]{5}[A-Z]$'
       and left(regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g'), 8) = v_doc;
    if a.id_contador is null or b.id_contador is null or a.id_contador = b.id_contador
       or a.farmacia <> b.farmacia
       or a.id_recepcion is null or a.id_recepcion is distinct from b.id_recepcion
       or public.cf_id_proveedor_comparable(a.id_proveedor)
          is distinct from public.cf_id_proveedor_comparable(b.id_proveedor) then
        return false;
    end if;
    v_op_b := regexp_replace(upper(b.numero_albaran), '[^A-Z0-9]', '', 'g');
    if v_op_b !~ '^08[A-Z][0-9]{5}[A-Z]$' or left(v_op_b, 8) <> v_doc
       or abs(a.fecha - e.fecha_albaran) > 15 or abs(b.fecha - e.fecha_albaran) > 15 then
        return false;
    end if;
    return abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500;
end;
$$;

comment on function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb) is
    'Revalida una linea UNO_A_VARIOS: pareja R17 (24: numero + interno de la misma recepcion) o R20 (36: numero '
    'exacto + su variante con letra final, misma recepcion, fechas a +-15 dias). Solo el propietario.';

commit;
