from src.database.leer_albaranes import obtener_ultimos_albaranes
from src.supabase_client.guardar_albaranes import guardar_albaran


def main() -> None:
    albaranes = obtener_ultimos_albaranes()

    if not albaranes:
        print("No se han encontrado albaranes en Farmatic.")
        return

    primer_albaran = albaranes[0]

    albaran_para_supabase = {
        "farmacia": "RITA",
        "id_contador": primer_albaran.IdContador,
        "id_proveedor": primer_albaran.IdProveedor.strip(),
        "proveedor": primer_albaran.Proveedor,
        "numero_albaran": primer_albaran.IdAlbaran.strip(),
        "fecha": primer_albaran.Fecha.date().isoformat(),
        "importe_pvp": float(primer_albaran.ImportePVP),
        "importe_puc": float(primer_albaran.ImportePUC),
        "descuento": float(primer_albaran.Dto),
        "estado": "PENDIENTE",
        "observaciones": None,
    }

    resultado = guardar_albaran(albaran_para_supabase)

    if resultado:
        print("Albarán enviado a Supabase.")
        print(resultado)
    else:
        print("No se ha insertado ningún albarán nuevo.")


if __name__ == "__main__":
    main()