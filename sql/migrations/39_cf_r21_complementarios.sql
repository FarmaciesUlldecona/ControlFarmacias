-- Migracion 39 (R21, DECISIONES DE PIO 2026-11-24 y 2026-11-25): una linea del PDF casa con su albaran EXACTO (A) y
-- de 1 a 3 complementarios (internos de Farmatic o la variante de su numero con letra final) del mismo proveedor, de la
-- misma recepcion que A o, sin recepcion, del mismo dia que A (R21-D1 revisada por Pio el 2026-11-25). Diseno:
-- pruebas/auditoria_r21/DISENO.md seccion 9. Caso real: 08005707 / 08L82633 = 638,82 + 27,32 (Q039320/2026, misma
-- recepcion) + 21,99 (08L82633A, sin recepcion, mismo dia) = 688,13.
-- - Redefine public.cf_linea_r17_valida con la misma firma: acepta la pareja R17 (24) y la R20 (36) exactamente como
--   la 36 y, solo con la marca a true, la combinacion R21. No regenera cf_persistir_conciliacion (30): el rechazo sigue
--   siendo LINEA_R17_NO_VALIDA. create or replace conserva la ACL de la 24 (solo el propietario).
-- - R21: cargo de la propia factura con fecha; de 2 a 4 detalles; albaranes distintos, existentes, con PUC, de una sola
--   farmacia, y cada detalle aplica su PUC; exactamente un A con el numero exacto de la linea, no interno, a +-15 dias
--   de la linea y con proveedor; cada uno de los demas es interno o 08X99999 + una letra de ese numero, con PUC > 0,
--   el mismo proveedor que A (R9) y la misma recepcion (no nula) que A, o sin recepcion y la misma fecha que A; suma
--   dentro de 0,05.
-- - La unicidad de la combinacion y que un complementario no sea el numero de otra factura las comprueba solo el codigo
--   (como en R17).
-- - Marca y conmutador: cf_configuracion.conciliacion_r21 (default false, R21-D5; Pio la enciende tras el postcheck).
--   Es el unico dato que cambia: la columna nueva en la fila de configuracion.
-- No nombra el rol del sistema. Idempotente. Requiere la 38 (cada migracion exige la anterior) y la 36.
begin;

do $$
begin
    if to_regclass('public.cf_cashflow_saldos') is null then
        raise exception 'MIGRACION_38_AUSENTE';
    end if;
    if not exists (select 1 from information_schema.columns where table_schema = 'public'
                   and table_name = 'cf_configuracion' and column_name = 'conciliacion_r20') then
        raise exception 'MIGRACION_36_AUSENTE';
    end if;
end;
$$;

alter table public.cf_configuracion add column if not exists conciliacion_r21 boolean not null default false;
comment on column public.cf_configuracion.conciliacion_r21 is
    'R21 (migracion 39): el codigo casa una linea con su albaran exacto + 1 a 3 complementarios solo si esta columna '
    'existe y vale true; false apaga R21 sin rollback (decision de Pio, R21-D5: false por defecto).';

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
    v_total integer;
    v_n integer;
    v_internos integer;
    v_farmacias integer;
    v_doc text;
    v_op text;
    v_op_b text;
    v_suma numeric;
begin
    if p_linea is null or p_linea !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       or jsonb_typeof(p_detalles) <> 'array' or jsonb_array_length(p_detalles) not between 2 and 4 then
        return false;
    end if;
    v_total := jsonb_array_length(p_detalles);
    select * into e from public.facturas_albaranes_extraidos where id = p_linea::uuid;
    if e.id is null or e.factura_id <> p_factura_id or e.importe_total is null
       or e.tipo_movimiento is distinct from 'CARGO' then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_todos) d
     where d->>'factura_albaran_extraido_id' = p_linea;
    if v_n <> v_total then
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
    if v_n <> v_total then
        return false;
    end if;
    v_doc := regexp_replace(upper(coalesce(e.numero_albaran, '')), '[^A-Z0-9]', '', 'g');
    if v_doc = '' then
        return false;
    end if;

    if v_total = 2 then
        -- R17 (24) y R20 (36): las ramas de la 36, sin cambios de criterio; si no valen, se prueba R21.
        <<r17_r20>>
        begin
            if v_internos = 1 then
                -- R17: el albaran de su numero (exacto o letra final) + 1 interno de la misma recepcion.
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
                    exit r17_r20;
                end if;
                v_op := regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g');
                if not (v_op = v_doc or (v_op ~ '^08[A-Z][0-9]{5}[A-Z]$' and left(v_op, 8) = v_doc)) then
                    exit r17_r20;
                end if;
                if abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500 then
                    return true;
                end if;
                exit r17_r20;
            end if;

            if v_internos <> 0 or e.fecha_albaran is null then
                exit r17_r20;
            end if;
            -- R20: A con el numero exacto de la linea y B su variante con una letra final.
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
                exit r17_r20;
            end if;
            v_op_b := regexp_replace(upper(b.numero_albaran), '[^A-Z0-9]', '', 'g');
            if v_op_b !~ '^08[A-Z][0-9]{5}[A-Z]$' or left(v_op_b, 8) <> v_doc
               or abs(a.fecha - e.fecha_albaran) > 15 or abs(b.fecha - e.fecha_albaran) > 15 then
                exit r17_r20;
            end if;
            if abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500 then
                return true;
            end if;
        end;
    end if;

    -- R21 (39): A + 1 a 3 complementarios, solo con la marca conciliacion_r21 a true.
    if (select c.conciliacion_r21 is not true from public.cf_configuracion c where c.id)
       or e.fecha_albaran is null then
        return false;
    end if;
    select count(distinct (x.farmacia, x.id_contador)), count(distinct x.farmacia)
      into v_n, v_farmacias
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint;
    if v_n <> v_total or v_farmacias <> 1 then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g') = v_doc;
    if v_n <> 1 then
        return false;
    end if;
    select x.* into a
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g') = v_doc;
    if upper(btrim(a.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$' or abs(a.fecha - e.fecha_albaran) > 15
       or public.cf_id_proveedor_comparable(a.id_proveedor) is null then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where x.id_contador <> a.id_contador
       and x.importe_puc > 0
       and (upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$'
            or (regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g') ~ '^08[A-Z][0-9]{5}[A-Z]$'
                and left(regexp_replace(upper(x.numero_albaran), '[^A-Z0-9]', '', 'g'), 8) = v_doc))
       and public.cf_id_proveedor_comparable(x.id_proveedor) = public.cf_id_proveedor_comparable(a.id_proveedor)
       and ((a.id_recepcion is not null and x.id_recepcion = a.id_recepcion)
            or (x.id_recepcion is null and x.fecha = a.fecha));
    if v_n <> v_total - 1 then
        return false;
    end if;
    select sum(x.importe_puc) into v_suma
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint;
    return abs(v_suma - e.importe_total) <= 0.0500;
end;
$$;

comment on function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb) is
    'Revalida una linea UNO_A_VARIOS: pareja R17 (24: numero + interno de la misma recepcion), R20 (36: numero '
    'exacto + su variante con letra final, misma recepcion, fechas a +-15 dias) o, con conciliacion_r21, R21 (39: '
    'numero exacto + 1 a 3 internos o variantes del mismo proveedor, de la misma recepcion que A o sin recepcion y '
    'del mismo dia). Solo el propietario.';

commit;
