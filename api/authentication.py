from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import Usuario
from .security import AuthTokenError, decode_access_token


class JWTAuthentication(BaseAuthentication):
	www_authenticate_realm = "api"

	def authenticate(self, request):
		auth = get_authorization_header(request).split()
		if not auth:
			return None

		if auth[0].lower() != b"bearer":
			return None

		if len(auth) != 2:
			raise AuthenticationFailed("Encabezado Authorization inválido")

		try:
			raw_token = auth[1].decode("utf-8")
		except UnicodeDecodeError as exc:
			raise AuthenticationFailed("Token inválido") from exc

		try:
			payload = decode_access_token(raw_token)
		except AuthTokenError as exc:
			raise AuthenticationFailed(str(exc)) from exc

		usuario = Usuario.objects.filter(id_usuario=payload["sub"]).first()
		if not usuario:
			raise AuthenticationFailed("Usuario no encontrado")

		return usuario, payload

	def authenticate_header(self, request):
		return f'Bearer realm="{self.www_authenticate_realm}"'
