# server/api/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	CuestionarioViewSet,
	IntentoViewSet,
	OpcionViewSet,
	PreguntaViewSet,
	UsuarioViewSet,
	auth_login,
	auth_logout,
	auth_me,
	auth_refresh,
	auth_register,
	cuestionario_pregunta_detail,
	cuestionario_pregunta_list_create,
	plantilla_propia_delete,
	plantilla_predeterminada_list,
	plantilla_propia_list,
	plantilla_propia_upload,
	respuesta_estudiante_detail,
	respuesta_estudiante_list_create,
)

router = DefaultRouter()
router.register(r"usuarios", UsuarioViewSet, basename="usuario")
router.register(r"preguntas", PreguntaViewSet, basename="pregunta")
router.register(r"opciones", OpcionViewSet, basename="opcion")
router.register(r"cuestionarios", CuestionarioViewSet, basename="cuestionario")
router.register(r"intentos", IntentoViewSet, basename="intento")

urlpatterns = [
	path("", include(router.urls)),
	path("auth/register/", auth_register, name="auth-register"),
	path("auth/login/", auth_login, name="auth-login"),
	path("auth/refresh/", auth_refresh, name="auth-refresh"),
	path("auth/logout/", auth_logout, name="auth-logout"),
	path("auth/me/", auth_me, name="auth-me"),
	path("plantillas/propias/", plantilla_propia_list, name="plantilla-propia-list"),
	path(
		"plantillas/predeterminadas/",
		plantilla_predeterminada_list,
		name="plantilla-predeterminada-list",
	),
	path("plantillas/propias/upload/", plantilla_propia_upload, name="plantilla-propia-upload"),
	path(
		"plantillas/propias/<str:template_name>/",
		plantilla_propia_delete,
		name="plantilla-propia-delete",
	),
	path(
		"cuestionario-preguntas/",
		cuestionario_pregunta_list_create,
		name="cuestionario-pregunta-list-create",
	),
	path(
		"cuestionario-preguntas/<int:cuestionario_id>/<int:pregunta_id>/",
		cuestionario_pregunta_detail,
		name="cuestionario-pregunta-detail",
	),
	path(
		"respuestas-estudiante/",
		respuesta_estudiante_list_create,
		name="respuesta-estudiante-list-create",
	),
	path(
		"respuestas-estudiante/<int:intento_id>/<int:pregunta_id>/",
		respuesta_estudiante_detail,
		name="respuesta-estudiante-detail",
	),
]
