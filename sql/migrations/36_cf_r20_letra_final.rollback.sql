-- Rollback de la migracion 36 (R20): devuelve el esquema exacto de la 35.
-- Restaura el texto exacto de cf_linea_r17_valida de la migracion 24 (solo R17), quita su comentario y la columna
-- cf_configuracion.conciliacion_r20. No toca conciliaciones: las lineas R20 ya persistidas siguen como datos, pero una
-- nueva no persistiria (LINEA_R17_NO_VALIDA) y el codigo, sin la columna, no la propone. create or replace conserva
-- la ACL (solo el propietario). Solo con confirmacion de Pio. Idempotente.
begin;

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
    if v_n <> 2 or v_internos <> 1 then
        return false;
    end if;
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
    -- El albaran de su numero: exacto o letra final (normalizados como en conciliacion.py).
    v_doc := regexp_replace(upper(coalesce(e.numero_albaran, '')), '[^A-Z0-9]', '', 'g');
    v_op := regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g');
    if v_doc = '' or not (v_op = v_doc or (v_op ~ '^08[A-Z][0-9]{5}[A-Z]$' and left(v_op, 8) = v_doc)) then
        return false;
    end if;
    return abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500;
end;
$$;

comment on function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb) is null;

alter table public.cf_configuracion drop column if exists conciliacion_r20;

commit;
