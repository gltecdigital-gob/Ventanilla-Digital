import re

from django import forms

from simuladores.curp import normalizar, validar_formato

from .models import VerificacionPresencial


class CurpForm(forms.Form):
    curp = forms.CharField(
        label="CURP", max_length=24,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters", "spellcheck": "false",
                                      "placeholder": "18 caracteres"}),
        help_text='¿No la recuerdas? Consúltala gratis en <a href="https://www.gob.mx/curp/" rel="noopener">gob.mx/curp</a>.',
    )

    def clean_curp(self):
        curp = normalizar(self.cleaned_data["curp"])
        valida, motivo = validar_formato(curp)
        if not valida:
            raise forms.ValidationError(motivo)
        return curp


class IdentidadForm(forms.Form):
    nombres = forms.CharField(label="Nombre o nombres", max_length=120, widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    primer_apellido = forms.CharField(label="Primer apellido", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "family-name"}))


TELEFONO = re.compile(r"^\d{10}$")


def _telefono(valor):
    digitos = re.sub(r"\D", "", valor or "")
    if digitos.startswith("52") and len(digitos) == 12:
        digitos = digitos[2:]
    if not TELEFONO.match(digitos):
        raise forms.ValidationError("Escribe un celular de 10 dígitos.")
    return digitos


class ContactoForm(forms.Form):
    MEDIOS = [("correo", "Correo electrónico"), ("telefono", "Mensaje de texto al celular")]
    medio = forms.ChoiceField(label="¿Dónde quieres recibir tus códigos de acceso?", choices=MEDIOS, widget=forms.RadioSelect, initial="correo")
    correo = forms.EmailField(label="Correo electrónico", required=False, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    telefono = forms.CharField(label="Celular (10 dígitos)", required=False, max_length=16,
                               widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "numeric"}))

    def clean(self):
        datos = super().clean()
        medio = datos.get("medio")
        if medio == "correo":
            if not datos.get("correo"):
                self.add_error("correo", "Escribe tu correo electrónico.")
            datos["destino"] = (datos.get("correo") or "").lower()
        elif medio == "telefono":
            try:
                datos["destino"] = _telefono(datos.get("telefono"))
            except forms.ValidationError as error:
                self.add_error("telefono", error)
        return datos


class CodigoForm(forms.Form):
    codigo = forms.CharField(
        label="Código de 6 dígitos", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "pattern": r"\d{6}"}),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip()
        if not codigo.isdigit():
            raise forms.ValidationError("El código solo tiene números.")
        return codigo


class AvisoForm(forms.Form):
    acepto = forms.BooleanField(label="Leí y acepto el aviso de privacidad", required=True)


class VerificacionForm(forms.Form):
    tipo_identificacion = forms.ChoiceField(label="Identificación que presentó", choices=VerificacionPresencial.TipoIdentificacion.choices)
    ultimos_digitos = forms.CharField(label="Últimos 4 caracteres del documento", max_length=4, min_length=4)
    cotejo = forms.BooleanField(
        label="Comparé en persona la fotografía de la identificación con quien la presenta, y el nombre coincide con el de RENAPO",
        required=True,
    )

    def clean_ultimos_digitos(self):
        valor = self.cleaned_data["ultimos_digitos"].strip().upper()
        if not valor.isalnum():
            raise forms.ValidationError("Solo letras y números.")
        return valor


class AltaVentanillaForm(VerificacionForm):
    aviso = forms.BooleanField(
        label="La persona recibió el aviso de privacidad (impreso o leído en voz alta) y lo aceptó",
        required=True,
    )


class ContactoVentanillaForm(ContactoForm):
    """Igual que en línea, pero la persona lee el código en su teléfono frente al personal."""
