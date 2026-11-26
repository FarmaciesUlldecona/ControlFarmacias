-- Rollback de la migracion 39 (R21): devuelve el esquema exacto de la 38.
-- Aborta (falla cerrado) si alguna conciliacion vigente tiene una linea R21: el validador de la 36 no la aceptaria al
-- volver a conciliar. Si no, restaura el texto exacto de cf_linea_r17_valida y su comentario de la 36 (R17 + R20) y
-- quita la columna cf_configuracion.conciliacion_r21. create or replace conserva la ACL (solo el propietario). Solo con
-- confirmacion de Pio. Idempotente.
begin;

do $$
begin
    if exists (select 1 from public.conciliacion_detalles d
                 join public.conciliaciones c on c.id = d.conciliacion_id
                where c.es_actual and d.provenance->>'regla' = 'R21') then
        raise exception 'ROLLBACK_39_CON_LINEAS_R21_VIGENTES';
    end if;
end;
$$;

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

alter table public.cf_configuracion drop column if exists conciliacion_r21;

commit;
