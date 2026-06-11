"""Pruebas rápidas del servicio SOAP con requests (evidencia técnica)."""
import requests, sys

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/soap"
NS = "techstore.soap.facturacion"

def llamar(cuerpo):
    env = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:fac="{NS}">
  <soapenv:Body>{cuerpo}</soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(URL, data=env.encode(), headers={"Content-Type": "text/xml"})
    print(r.status_code, "\n", r.text, "\n", "-" * 70)

# 1) ValidarFactura con XML válido
llamar(f"""<fac:ValidarFactura><fac:xmlFactura>
&lt;Factura&gt;&lt;Cliente&gt;Alex Maigua&lt;/Cliente&gt;&lt;Producto&gt;Laptop&lt;/Producto&gt;&lt;Cantidad&gt;1&lt;/Cantidad&gt;&lt;Total&gt;850.00&lt;/Total&gt;&lt;/Factura&gt;
</fac:xmlFactura></fac:ValidarFactura>""")

# 2) GenerarFacturaXML de la compra 1
llamar("<fac:GenerarFacturaXML><fac:idCompra>1</fac:idCompra></fac:GenerarFacturaXML>")

# 3) ConsultarComprobante de la compra 1
llamar("<fac:ConsultarComprobante><fac:idCompra>1</fac:idCompra></fac:ConsultarComprobante>")
