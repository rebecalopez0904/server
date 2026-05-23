# server/api/views.py
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
	Cuestionario,
	CuestionarioPregunta,
	Intento,
	Opcion,
	Pregunta,
	RespuestaEstudiante,
	Usuario,
)
from .serializers import (
	AuthLoginSerializer,
	AuthRegisterSerializer,
	CuestionarioPreguntaSerializer,
	CuestionarioSerializer,
	IntentoSerializer,
	OpcionSerializer,
	PreguntaSerializer,
	RespuestaEstudianteSerializer,
	UsuarioSerializer,
)
from .security import (
	AuthTokenError,
	create_access_token,
	issue_refresh_token,
	revoke_refresh_token,
	rotate_refresh_token,
	verify_password,
)
from .template_storage import (
	ensure_templates_media_structure,
	normalize_template_relative_path,
	normalize_user_folder_name,
	resolve_custom_template_storage_path,
)


ALLOWED_TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


def _is_predeterminada(pregunta: Pregunta) -> bool:
	return pregunta.usuario_creador_id is None


def _set_refresh_cookie(response, raw_token, expires_at):
	max_age = max(int((expires_at - timezone.now()).total_seconds()), 0)
	response.set_cookie(
		settings.JWT_REFRESH_COOKIE_NAME,
		raw_token,
		max_age=max_age,
		httponly=True,
		secure=settings.JWT_REFRESH_COOKIE_SECURE,
		samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
		path="/api/auth/",
	)


def _clear_refresh_cookie(response):
	response.delete_cookie(
		settings.JWT_REFRESH_COOKIE_NAME,
		path="/api/auth/",
		samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
	)


def _validate_profesor_role(request):
	if not getattr(request.user, "is_authenticated", False):
		return Response(
			{"detail": "No autenticado."},
			status=status.HTTP_401_UNAUTHORIZED,
		)
	if request.user.rol != "profesor":
		return Response(
			{"detail": "Solo los profesores pueden gestionar plantillas propias."},
			status=status.HTTP_403_FORBIDDEN,
		)
	return None


def _get_template_upload_max_size() -> int:
	return max(int(getattr(settings, "TEMPLATE_UPLOAD_MAX_SIZE", 5 * 1024 * 1024)), 1)


def _build_template_response_payload(request, template_file_path: Path) -> dict:
	relative_path = template_file_path.relative_to(settings.MEDIA_ROOT).as_posix()
	plantilla_url = f"{settings.MEDIA_URL.rstrip('/')}/{relative_path}"
	return {
		"nombre_archivo": template_file_path.name,
		"tamano_bytes": template_file_path.stat().st_size,
		"plantilla_path": relative_path,
		"plantilla_url": plantilla_url,
		"plantilla_url_absoluta": request.build_absolute_uri(plantilla_url),
	}


def _extract_template_filename(template_value: str) -> str | None:
	raw_value = str(template_value or "").strip()
	if not raw_value:
		return None

	normalized = raw_value.replace("\\", "/")
	parsed_path = urlparse(normalized).path if "://" in normalized else normalized
	filename = Path(unquote(parsed_path)).name.strip()
	if not filename:
		return None
	if Path(filename).suffix.lower() not in ALLOWED_TEMPLATE_EXTENSIONS:
		return None
	return filename


def _cleanup_question_template_if_unused(
	owner_id: int | None,
	template_value: str,
	exclude_question_id: int | None = None,
) -> None:
	if owner_id is None:
		return

	template_name = _extract_template_filename(template_value)
	if template_name is None:
		return

	try:
		storage_path = resolve_custom_template_storage_path(owner_id, template_name)
	except (ValueError, SuspiciousFileOperation):
		return

	if not storage_path.exists() or not storage_path.is_file():
		return

	relative_path = storage_path.relative_to(settings.MEDIA_ROOT).as_posix()
	plantilla_url = f"{settings.MEDIA_URL.rstrip('/')}/{relative_path}"
	reference_query = Pregunta.objects.filter(
		Q(plantilla_url=relative_path)
		| Q(plantilla_url=relative_path.replace("/", "\\"))
		| Q(plantilla_url=plantilla_url)
		| Q(plantilla_url=plantilla_url.lstrip("/"))
		| Q(plantilla_url__endswith=relative_path)
		| Q(plantilla_url__endswith=plantilla_url)
	)
	if exclude_question_id is not None:
		reference_query = reference_query.exclude(id_pregunta=exclude_question_id)
	if reference_query.exists():
		return

	storage_path.unlink()


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_register(request):
	auth_serializer = AuthRegisterSerializer(data=request.data)
	auth_serializer.is_valid(raise_exception=True)
	data = auth_serializer.validated_data
	normalized_email = data["correo"].strip().lower()

	if Usuario.objects.filter(correo__iexact=normalized_email).exists():
		return Response(
			{"detail": "Ya existe un usuario con ese correo."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	with transaction.atomic():
		usuario_serializer = UsuarioSerializer(
			data={
				"nombre_usuario": data["nombre_usuario"].strip(),
				"apellido_usuario": data["apellido_usuario"].strip(),
				"correo": normalized_email,
				"contrasena": data["contrasena"],
				"rol": data["rol"],
			}
		)
		usuario_serializer.is_valid(raise_exception=True)
		usuario = usuario_serializer.save()
		access_token = create_access_token(usuario)
		refresh_token, refresh_expires_at = issue_refresh_token(usuario)

	response = Response(
		{"access_token": access_token, "user": UsuarioSerializer(usuario).data},
		status=status.HTTP_201_CREATED,
	)
	_set_refresh_cookie(response, refresh_token, refresh_expires_at)
	return response


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_login(request):
	auth_serializer = AuthLoginSerializer(data=request.data)
	auth_serializer.is_valid(raise_exception=True)
	data = auth_serializer.validated_data
	normalized_email = data["correo"].strip().lower()
	usuario = Usuario.objects.filter(correo__iexact=normalized_email).first()

	if usuario is None or not verify_password(data["contrasena"], usuario.contrasena):
		return Response(
			{"detail": "Correo o contrasena incorrectos."},
			status=status.HTTP_401_UNAUTHORIZED,
		)

	access_token = create_access_token(usuario)
	refresh_token, refresh_expires_at = issue_refresh_token(usuario)
	response = Response(
		{"access_token": access_token, "user": UsuarioSerializer(usuario).data}
	)
	_set_refresh_cookie(response, refresh_token, refresh_expires_at)
	return response


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_refresh(request):
	raw_refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
	if not raw_refresh_token:
		return Response(
			{"detail": "No hay refresh token activo."},
			status=status.HTTP_401_UNAUTHORIZED,
		)

	try:
		usuario, new_refresh_token, refresh_expires_at = rotate_refresh_token(
			raw_refresh_token
		)
	except AuthTokenError as exc:
		response = Response(
			{"detail": str(exc)},
			status=status.HTTP_401_UNAUTHORIZED,
		)
		_clear_refresh_cookie(response)
		return response

	response = Response(
		{
			"access_token": create_access_token(usuario),
			"user": UsuarioSerializer(usuario).data,
		}
	)
	_set_refresh_cookie(response, new_refresh_token, refresh_expires_at)
	return response


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_logout(request):
	raw_refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
	if raw_refresh_token:
		try:
			revoke_refresh_token(raw_refresh_token)
		except AuthTokenError:
			pass

	response = Response(status=status.HTTP_204_NO_CONTENT)
	_clear_refresh_cookie(response)
	return response


@api_view(["GET"])
def auth_me(request):
	if not getattr(request.user, "is_authenticated", False):
		return Response(
			{"detail": "No autenticado."},
			status=status.HTTP_401_UNAUTHORIZED,
		)
	return Response({"user": UsuarioSerializer(request.user).data})


class UsuarioViewSet(viewsets.ModelViewSet):
	queryset = Usuario.objects.all().order_by("id_usuario")
	serializer_class = UsuarioSerializer


class PreguntaViewSet(viewsets.ModelViewSet):
	queryset = Pregunta.objects.all().order_by("id_pregunta")
	serializer_class = PreguntaSerializer

	def perform_create(self, serializer):
		if serializer.validated_data.get("usuario_creador") is None:
			raise PermissionDenied(
				"Las preguntas predeterminadas son de solo lectura y no se pueden crear aquí."
			)
		serializer.save()

	def perform_update(self, serializer):
		if _is_predeterminada(serializer.instance):
			raise PermissionDenied("Las preguntas predeterminadas son de solo lectura.")
		previous_template = serializer.instance.plantilla_url
		updated_question = serializer.save()
		if (previous_template or "").strip() != (
			updated_question.plantilla_url or ""
		).strip():
			_cleanup_question_template_if_unused(
				updated_question.usuario_creador_id,
				previous_template,
				exclude_question_id=updated_question.id_pregunta,
			)

	def perform_destroy(self, instance):
		if _is_predeterminada(instance):
			raise PermissionDenied("Las preguntas predeterminadas son de solo lectura.")
		owner_id = instance.usuario_creador_id
		template_value = instance.plantilla_url
		instance.delete()
		_cleanup_question_template_if_unused(owner_id, template_value)


class OpcionViewSet(viewsets.ModelViewSet):
	queryset = Opcion.objects.all().order_by("id_opcion")
	serializer_class = OpcionSerializer

	def perform_create(self, serializer):
		pregunta = serializer.validated_data["pregunta"]
		if _is_predeterminada(pregunta):
			raise PermissionDenied(
				"No se pueden crear opciones para preguntas predeterminadas."
			)
		serializer.save()

	def perform_update(self, serializer):
		current_question = serializer.instance.pregunta
		target_question = serializer.validated_data.get("pregunta", current_question)
		if _is_predeterminada(current_question) or _is_predeterminada(target_question):
			raise PermissionDenied(
				"No se pueden modificar opciones de preguntas predeterminadas."
			)
		serializer.save()

	def perform_destroy(self, instance):
		if _is_predeterminada(instance.pregunta):
			raise PermissionDenied(
				"No se pueden eliminar opciones de preguntas predeterminadas."
			)
		instance.delete()


class CuestionarioViewSet(viewsets.ModelViewSet):
	queryset = Cuestionario.objects.all().order_by("id_cuestionario")
	serializer_class = CuestionarioSerializer


class IntentoViewSet(viewsets.ModelViewSet):
	queryset = Intento.objects.all().order_by("id_intento")
	serializer_class = IntentoSerializer


@api_view(["GET", "POST"])
def cuestionario_pregunta_list_create(request):
	if request.method == "GET":
		queryset = CuestionarioPregunta.objects.select_related(
			"cuestionario", "pregunta"
		).all()
		serializer = CuestionarioPreguntaSerializer(queryset, many=True)
		return Response(serializer.data)

	serializer = CuestionarioPreguntaSerializer(data=request.data)
	if serializer.is_valid():
		serializer.save()
		return Response(serializer.data, status=status.HTTP_201_CREATED)
	return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def cuestionario_pregunta_detail(request, cuestionario_id, pregunta_id):
	instance = get_object_or_404(
		CuestionarioPregunta,
		cuestionario_id=cuestionario_id,
		pregunta_id=pregunta_id,
	)

	if request.method == "GET":
		serializer = CuestionarioPreguntaSerializer(instance)
		return Response(serializer.data)

	if request.method in ["PUT", "PATCH"]:
		serializer = CuestionarioPreguntaSerializer(
			instance,
			data=request.data,
			partial=request.method == "PATCH",
		)
		if serializer.is_valid():
			serializer.save()
			return Response(serializer.data)
		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

	instance.delete()
	return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
def respuesta_estudiante_list_create(request):
	if request.method == "GET":
		queryset = RespuestaEstudiante.objects.select_related(
			"intento", "pregunta", "opc_select"
		).all()
		serializer = RespuestaEstudianteSerializer(queryset, many=True)
		return Response(serializer.data)

	serializer = RespuestaEstudianteSerializer(data=request.data)
	if serializer.is_valid():
		serializer.save()
		return Response(serializer.data, status=status.HTTP_201_CREATED)
	return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def respuesta_estudiante_detail(request, intento_id, pregunta_id):
	instance = get_object_or_404(
		RespuestaEstudiante,
		intento_id=intento_id,
		pregunta_id=pregunta_id,
	)

	if request.method == "GET":
		serializer = RespuestaEstudianteSerializer(instance)
		return Response(serializer.data)

	if request.method in ["PUT", "PATCH"]:
		serializer = RespuestaEstudianteSerializer(
			instance,
			data=request.data,
			partial=request.method == "PATCH",
		)
		if serializer.is_valid():
			serializer.save()
			return Response(serializer.data)
		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

	instance.delete()
	return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def plantilla_propia_upload(request):
	role_error_response = _validate_profesor_role(request)
	if role_error_response is not None:
		return role_error_response

	archivo = request.FILES.get("archivo") or request.FILES.get("file")
	if archivo is None:
		return Response(
			{"detail": "Debes adjuntar un archivo en el campo 'archivo'."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	extension = Path(archivo.name).suffix.lower()
	if extension not in ALLOWED_TEMPLATE_EXTENSIONS:
		return Response(
			{"detail": "Tipo de archivo no permitido."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	max_size = _get_template_upload_max_size()
	if archivo.size > max_size:
		return Response(
			{
				"detail": (
					f"El archivo excede el tamaño máximo permitido de {max_size} bytes."
				)
			},
			status=status.HTTP_400_BAD_REQUEST,
		)

	base_name = slugify(Path(archivo.name).stem) or "plantilla"
	safe_file_name = f"{base_name[:60]}_{uuid4().hex}{extension}"

	try:
		storage_path = resolve_custom_template_storage_path(
			request.user.id_usuario,
			safe_file_name,
			create_parent=True,
		)
	except (ValueError, SuspiciousFileOperation):
		return Response(
			{"detail": "No fue posible generar una ruta segura para la plantilla."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	with storage_path.open("wb+") as destination:
		for chunk in archivo.chunks():
			destination.write(chunk)

	return Response(
		_build_template_response_payload(request, storage_path),
		status=status.HTTP_201_CREATED,
	)


@api_view(["GET"])
def plantilla_propia_list(request):
	role_error_response = _validate_profesor_role(request)
	if role_error_response is not None:
		return role_error_response

	structure = ensure_templates_media_structure()
	user_folder = normalize_user_folder_name(request.user.id_usuario)
	user_dir = structure["propias"] / user_folder
	user_dir.mkdir(parents=True, exist_ok=True)

	plantillas = []
	for file_path in sorted(user_dir.iterdir(), key=lambda current: current.name.lower()):
		if not file_path.is_file():
			continue
		if file_path.suffix.lower() not in ALLOWED_TEMPLATE_EXTENSIONS:
			continue
		plantillas.append(_build_template_response_payload(request, file_path))

	return Response({"results": plantillas})


@api_view(["GET"])
def plantilla_predeterminada_list(request):
	role_error_response = _validate_profesor_role(request)
	if role_error_response is not None:
		return role_error_response

	structure = ensure_templates_media_structure()
	default_dir = structure["predeterminadas"]
	default_dir.mkdir(parents=True, exist_ok=True)

	plantillas = []
	for file_path in sorted(default_dir.iterdir(), key=lambda current: current.name.lower()):
		if not file_path.is_file():
			continue
		if file_path.suffix.lower() not in ALLOWED_TEMPLATE_EXTENSIONS:
			continue
		plantillas.append(_build_template_response_payload(request, file_path))

	return Response({"results": plantillas})


@api_view(["DELETE"])
def plantilla_propia_delete(request, template_name):
	role_error_response = _validate_profesor_role(request)
	if role_error_response is not None:
		return role_error_response

	try:
		normalized_name = normalize_template_relative_path(template_name)
	except SuspiciousFileOperation:
		return Response(
			{"detail": "Nombre de plantilla inválido."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	if len(normalized_name.parts) != 1:
		return Response(
			{"detail": "Solo se permite eliminar plantillas del directorio raíz propio."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	if Path(normalized_name.name).suffix.lower() not in ALLOWED_TEMPLATE_EXTENSIONS:
		return Response(
			{"detail": "Tipo de plantilla no permitido."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	try:
		storage_path = resolve_custom_template_storage_path(
			request.user.id_usuario,
			normalized_name.as_posix(),
		)
	except (ValueError, SuspiciousFileOperation):
		return Response(
			{"detail": "No fue posible resolver una ruta segura para la plantilla."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	if not storage_path.exists() or not storage_path.is_file():
		return Response(
			{"detail": "Plantilla no encontrada."},
			status=status.HTTP_404_NOT_FOUND,
		)

	template_data = _build_template_response_payload(request, storage_path)
	reference_candidates = {
		template_data["plantilla_path"],
		template_data["plantilla_path"].replace("/", "\\"),
		template_data["plantilla_url"],
		template_data["plantilla_url"].lstrip("/"),
		template_data["plantilla_url_absoluta"],
	}
	in_use = Pregunta.objects.filter(
		Q(plantilla_url__in=reference_candidates)
	).exists()
	if in_use:
		return Response(
			{"detail": "No se puede eliminar la plantilla porque está en uso por una pregunta."},
			status=status.HTTP_409_CONFLICT,
		)

	storage_path.unlink()
	return Response(status=status.HTTP_204_NO_CONTENT)
