"""
TECHSTORE 360 - Servicio SOAP de Facturación Electrónica (independiente)
Requerimiento 9. Operaciones mínimas:
  - ValidarFactura(xmlFactura)
  - GenerarFacturaXML(idCompra)
  - ConsultarComprobante(idCompra)
WSDL disponible en:  <URL>/soap?wsdl
"""
import os, json, random
from datetime import datetime
from xml.etree import ElementTree as ET

import psycopg2
from dotenv import load_dotenv
from spyne import Application, rpc, ServiceBase, Unicode, Integer
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------- utilidades

def _conexion():
    return psycopg2.connect(DATABASE_URL)

def _generar_clave_acceso(id_compra: int) -> str:
    """Simula la clave de acceso del SRI: FAC-AAAA-XXXXX + dígito (módulo 11 simplificado)."""
    secuencial = f"{id_compra:05d}"
    base = f"{datetime.now().year}{secuencial}{random.randint(10, 99)}"
    pesos, suma = [2, 3, 4, 5, 6, 7], 0
    for i, d in enumerate(reversed(base)):
        suma += int(d) * pesos[i % len(pesos)]
    dv = 11 - (suma % 11)
    dv = 0 if dv == 11 else (1 if dv == 10 else dv)
    return f"FAC-{datetime.now().year}-{secuencial}{dv}"

def _respuesta(estado: str, mensaje: str, clave: str = "") -> str:
    return (
        "<RespuestaFactura>"
        f"<Estado>{estado}</Estado>"
        f"<Mensaje>{mensaje}</Mensaje>"
        f"<ClaveAcceso>{clave}</ClaveAcceso>"
        "</RespuestaFactura>"
    )

# ---------------------------------------------------------------- servicio

class FacturacionService(ServiceBase):

    @rpc(Unicode, _returns=Unicode)
    def ValidarFactura(ctx, xmlFactura):
        """Recibe los datos de una compra en XML y valida la información."""
        try:
            root = ET.fromstring(xmlFactura)
        except ET.ParseError as e:
            return _respuesta("RECHAZADA", f"XML mal formado: {e}")

        cliente = root.findtext("Cliente")
        total = root.findtext("Total")
        errores = []
        if not cliente or not cliente.strip():
            errores.append("Falta el Cliente")
        try:
            if total is None or float(total) <= 0:
                errores.append("Total debe ser mayor a 0")
        except (TypeError, ValueError):
            errores.append("Total no es numérico")

        if errores:
            return _respuesta("RECHAZADA", "; ".join(errores))
        return _respuesta("VALIDADA", "Factura validada correctamente",
                          _generar_clave_acceso(random.randint(1, 99999)))

    @rpc(Integer, _returns=Unicode)
    def GenerarFacturaXML(ctx, idCompra):
        """Lee la compra de Supabase, genera la factura XML, simula la clave
        de acceso y actualiza el estado de la compra."""
        conn = None
        try:
            conn = _conexion()
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.items, c.subtotal, c.iva, c.total, c.creado_en,
                       u.nombre, u.email
                FROM compras c JOIN usuarios u ON u.id = c.usuario_id
                WHERE c.id = %s
            """, (idCompra,))
            fila = cur.fetchone()
            if not fila:
                return _respuesta("RECHAZADA", f"La compra {idCompra} no existe")

            (cid, items, subtotal, iva, total, fecha, nombre, email) = fila
            if isinstance(items, str):
                items = json.loads(items)
            clave = _generar_clave_acceso(cid)

            detalles = "".join(
                "<Detalle>"
                f"<Producto>{i['nombre']}</Producto>"
                f"<Cantidad>{i['cantidad']}</Cantidad>"
                f"<PrecioUnitario>{i['precio_unitario']:.2f}</PrecioUnitario>"
                f"<Subtotal>{i['subtotal']:.2f}</Subtotal>"
                "</Detalle>"
                for i in items
            )
            factura_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Factura>"
                f"<ClaveAcceso>{clave}</ClaveAcceso>"
                f"<Fecha>{fecha.isoformat()}</Fecha>"
                f"<Cliente>{nombre}</Cliente>"
                f"<Email>{email}</Email>"
                f"<Detalles>{detalles}</Detalles>"
                f"<Subtotal>{float(subtotal):.2f}</Subtotal>"
                f"<IVA>{float(iva):.2f}</IVA>"
                f"<Total>{float(total):.2f}</Total>"
                "<Estado>VALIDADA</Estado>"
                "</Factura>"
            )

            cur.execute(
                "UPDATE compras SET estado = 'VALIDADA', clave_acceso = %s WHERE id = %s",
                (clave, cid),
            )
            conn.commit()
            
            factura_xml_limpia = factura_xml.replace(
                '<?xml version="1.0" encoding="UTF-8"?>',
                ''
            )

            return (
                "<RespuestaFactura>"
                "<Estado>VALIDADA</Estado>"
                "<Mensaje>Factura generada correctamente</Mensaje>"
                f"<ClaveAcceso>{clave}</ClaveAcceso>"
                f"<FacturaXML>{factura_xml_limpia}</FacturaXML>"
                "</RespuestaFactura>"
            )
        except Exception as e:
            if conn:
                conn.rollback()
            return _respuesta("ERROR", f"Error interno: {e}")
        finally:
            if conn:
                conn.close()  # finally: liberar SIEMPRE la conexión

    @rpc(Integer, _returns=Unicode)
    def ConsultarComprobante(ctx, idCompra):
        """Devuelve el estado actual de la factura de una compra."""
        conn = None
        try:
            conn = _conexion()
            cur = conn.cursor()
            cur.execute(
                "SELECT estado, clave_acceso, total FROM compras WHERE id = %s",
                (idCompra,),
            )
            fila = cur.fetchone()
            if not fila:
                return _respuesta("NO_ENCONTRADA", f"La compra {idCompra} no existe")
            estado, clave, total = fila
            return _respuesta(estado or "PENDIENTE",
                              f"Comprobante de la compra {idCompra} por ${float(total):.2f}",
                              clave or "")
        except Exception as e:
            return _respuesta("ERROR", f"Error interno: {e}")
        finally:
            if conn:
                conn.close()

# ---------------------------------------------------------------- servidor

soap_app = Application(
    [FacturacionService],
    tns="techstore.soap.facturacion",
    in_protocol=Soap11(validator="lxml"),
    out_protocol=Soap11(),
)
wsgi_soap = WsgiApplication(soap_app)

def application(environ, start_response):
    """Monta el SOAP en /soap (y /soap?wsdl para el contrato WSDL)."""
    path = environ.get("PATH_INFO", "")
    if path.startswith("/soap"):
        environ["PATH_INFO"] = path[len("/soap"):] or "/"
        return wsgi_soap(environ, start_response)
    start_response("200 OK", [("Content-Type", "application/json")])
    return [b'{"servicio":"TechStore 360 SOAP Facturacion","wsdl":"/soap?wsdl"}']

if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    port = int(os.getenv("PORT", 8000))
    print(f"SOAP escuchando en http://0.0.0.0:{port}/soap  (WSDL: /soap?wsdl)")
    make_server("0.0.0.0", port, application).serve_forever()
