import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from django.conf import settings
from django.utils import timezone as django_timezone

from .models import RefreshTokenSession


class AuthTokenError(Exception):
	pass


def _current_utc() -> datetime:
	return datetime.now(timezone.utc)


def _token_hash(raw_token: str) -> str:
	return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_password(raw_password: str) -> str:
	if not raw_password:
		raise ValueError("La contrasena no puede estar vacia")
	return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, hashed_password: str) -> bool:
	if not raw_password or not hashed_password:
		return False
	try:
		return bcrypt.checkpw(
			raw_password.encode("utf-8"),
			hashed_password.encode("utf-8"),
		)
	except ValueError:
		return False


def is_bcrypt_hash(value: str) -> bool:
	if not value:
		return False
	return value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")


def _encode_jwt(payload: dict) -> str:
	return jwt.encode(
		payload,
		settings.JWT_SECRET_KEY,
		algorithm=settings.JWT_ALGORITHM,
	)


def _decode_jwt(raw_token: str, verify_exp: bool = True) -> dict:
	options = {"verify_exp": verify_exp}
	try:
		return jwt.decode(
			raw_token,
			settings.JWT_SECRET_KEY,
			algorithms=[settings.JWT_ALGORITHM],
			options=options,
		)
	except jwt.ExpiredSignatureError as exc:
		raise AuthTokenError("El token expiró") from exc
	except jwt.InvalidTokenError as exc:
		raise AuthTokenError("Token inválido") from exc


def create_access_token(usuario) -> str:
	now = _current_utc()
	payload = {
		"sub": str(usuario.id_usuario),
		"rol": usuario.rol,
		"type": "access",
		"iat": int(now.timestamp()),
		"exp": int((now + timedelta(minutes=settings.JWT_ACCESS_MINUTES)).timestamp()),
	}
	return _encode_jwt(payload)


def _create_refresh_payload(usuario, jti: str, exp: datetime) -> dict:
	now = _current_utc()
	return {
		"sub": str(usuario.id_usuario),
		"rol": usuario.rol,
		"type": "refresh",
		"jti": jti,
		"iat": int(now.timestamp()),
		"exp": int(exp.timestamp()),
	}


def issue_refresh_token(usuario) -> tuple[str, datetime]:
	expiration = _current_utc() + timedelta(days=settings.JWT_REFRESH_DAYS)
	jti = str(uuid.uuid4())
	payload = _create_refresh_payload(usuario, jti, expiration)
	raw_token = _encode_jwt(payload)

	RefreshTokenSession.objects.create(
		usuario=usuario,
		jti=jti,
		token_hash=_token_hash(raw_token),
		expira_en=expiration,
	)
	return raw_token, expiration


def _get_refresh_record(payload: dict, raw_token: str) -> RefreshTokenSession:
	user_id = payload.get("sub")
	jti = payload.get("jti")
	token_type = payload.get("type")

	if token_type != "refresh" or not user_id or not jti:
		raise AuthTokenError("Refresh token inválido")

	record = (
		RefreshTokenSession.objects.select_related("usuario")
		.filter(
			usuario_id=user_id,
			jti=jti,
			revocado_en__isnull=True,
		)
		.first()
	)
	if not record:
		raise AuthTokenError("Refresh token no reconocido")

	if record.token_hash != _token_hash(raw_token):
		raise AuthTokenError("Refresh token no coincide")

	if record.expira_en <= django_timezone.now():
		raise AuthTokenError("Refresh token expirado")

	return record


def rotate_refresh_token(raw_token: str):
	payload = _decode_jwt(raw_token)
	record = _get_refresh_record(payload, raw_token)
	record.revocado_en = django_timezone.now()
	record.save(update_fields=["revocado_en"])
	return record.usuario, *issue_refresh_token(record.usuario)


def revoke_refresh_token(raw_token: str) -> None:
	payload = _decode_jwt(raw_token, verify_exp=False)
	record = _get_refresh_record(payload, raw_token)
	record.revocado_en = django_timezone.now()
	record.save(update_fields=["revocado_en"])


def decode_access_token(raw_token: str) -> dict:
	payload = _decode_jwt(raw_token)
	if payload.get("type") != "access":
		raise AuthTokenError("Token de acceso inválido")
	if not payload.get("sub"):
		raise AuthTokenError("Token sin sujeto")
	return payload
